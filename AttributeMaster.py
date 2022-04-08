# ============================================================
#
#           Attribute Master
#
# Attribute Master is designed to make the handling of attributes
# easier and faster. You can quickly change the state of attributes,
# rename, move by dragging and dropping and more.
#
# version: 0.2
# author: Matthew Denton
#
# TODO enum value editor
# TODO add mode to set min and max values of number attributes
# TODO Add a seperator mode which lets you change the name that is displayed in it
# TODO a method to easily copy attributes from one object to another and retain it's order
# TODO editable attribute values
# TODO option to switch between showing the attributes long name or it's value in the list
# TODO update the list automaticlly when an attribute is edited, added, removed etc
#
# ============================================================
from PySide2 import QtGui, QtWidgets
from PySide2 import QtCore
from PySide2.QtWidgets import *
from shiboken2 import wrapInstance
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
from maya import cmds, mel
from maya import OpenMayaUI
from maya.api import OpenMaya
import sys

__version__ = "0.3.0"

TOOL_NAME = "AttributeMasterTool"
WINDOW_TITLE = "Attribute Master"

data_types = ["Vector", "Integer", "String", "Double", "Boolean", "Enum"]

type_vector = 0
type_integer = 1
type_string = 2
type_double = 3
type_boolean = 4
type_enum = 5


def get_type_index(name):
    if name == "vector":
        return type_vector
    if name == "integer":
        return type_integer
    if name == "string":
        return type_string
    if name == "double":
        return type_double
    if name == "boolean":
        return type_boolean
    if name == "enum":
        return type_enum
    return type_double


def as_int(num):
    """
    Allows for support of both python 2 and 3, allowing for suppoer of maya versions
    before and after 2022.
    """
    if sys.version_info >= (3, 0):
        return int(num)
    return long(num)


def maya_main_window():
    main_window = OpenMayaUI.MQtUtil.mainWindow()
    return wrapInstance(as_int(main_window), QtWidgets.QWidget)


def deleteMayaWindowContext(name):
    control = TOOL_NAME + "WorkspaceControl"
    if cmds.workspaceControl(control, q=True, exists=True):
        cmds.workspaceControl(control, e=True, close=True)
        cmds.deleteUI(control, control=True)


def createSpacerItem(width=20, height=40):
    return QtWidgets.QSpacerItem(
        width, height, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)


class UndoStateContext(object):
    """
    The undo state is used to force undo commands to be registered when this
    tool is being used. Once the "with" statement is being exited, the default
    settings are restored.

    with UndoStateContext():
        # code
    """

    def __init__(self):
        self.state = cmds.undoInfo(query=True, state=True)
        self.infinity = cmds.undoInfo(query=True, infinity=True)
        self.length = cmds.undoInfo(query=True, length=True)

    def __enter__(self):
        cmds.undoInfo(state=True, infinity=True)

    def __exit__(self, *exc_info):
        cmds.undoInfo(
            state=self.state,
            infinity=self.infinity,
            length=self.length
        )


class UndoChunkContext(object):
    """
    The undo context is used to combine a chain of commands into one undo.
    Can be used in combination with the "with" statement.

    with UndoChunkContext():
        # code
    """

    def __enter__(self):
        cmds.undoInfo(openChunk=True)

    def __exit__(self, *exc_info):
        cmds.undoInfo(closeChunk=True)


class Attribute(QtWidgets.QWidget):
    """
    Stores the values of an attribute as an object for easy sorting and managing.
    """

    def __init__(self, ui, node, niceName, longName, locked=False, keyable=True, channelBox=False, type="double"):
        super(Attribute, self).__init__()
        self.ui = ui

        self.main_layout = QtWidgets.QHBoxLayout()
        self.main_layout.setMargin(3)
        self.setLayout(self.main_layout)

        self.node = node
        self.niceName = niceName
        self.longName = longName
        self.locked = locked
        self.keyable = keyable
        self.channelBox = channelBox
        self.type = type

        # Display State meta
        self.displayState = AttributeMaster.DISPLAY_LONGNAME

        if type == "enum":
            cmds.attributeQuery(longName, node=node, listEnum=True)

        self.create_ui()
        self.refresh()

    def exists(self):
        return cmds.attributeQuery(self.longName, node=self.node, exists=True)

    def is_keyable(self):
        return self.exists() and cmds.getAttr(self.path, keyable=True)

    def is_locked(self):
        return self.exists() and cmds.getAttr(self.path, lock=True)

    def is_hidden(self):
        return self.exists() and cmds.getAttr(self.path, channelBox=True) is False

    def is_seperator(self):
        return self.longName is not None and "__seperator_" in self.longName

    @property
    def path(self):
        return "{}.{}".format(self.node, self.longName)

    @property
    def hasMin(self):
        return self.exists() and cmds.attributeQuery(self.longName, node=self.node, minExists=True) \
            and (self.type == "integer" or self.type == "double")

    @property
    def hasMax(self):
        return self.exists() and cmds.attributeQuery(self.longName, node=self.node, maxExists=True) \
            and (self.type == "integer" or self.type == "double")

    @property
    def max(self):
        return cmds.attributeQuery(self.longName, node=self.node, max=True)

    @property
    def min(self):
        return cmds.attributeQuery(self.longName, node=self.node, min=True)

    def create_ui(self):
        """
        Creates all of the UI elements for the attribute to be displayed in the editor and
        makes any connections for buttons.
        """
        self.label = QtWidgets.QLabel(self.niceName, objectName="ShortName")
        self.labelLong = QtWidgets.QLabel(self.longName, objectName="LongName")
        self.deleteBtn = QtWidgets.QPushButton(
            icon=QtGui.QIcon(":/deleteActive.png"), objectName="DeleteBtn")
        self.deleteBtn.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
        self.deleteBtn.setToolTip("Delete attribute")
        self.deleteBtn.setToolTipDuration(5000)

        self.valueWidget = None

        self.editor = None

        self.deleteBtn.clicked.connect(self.__delete)

        self.main_layout.addWidget(self.label)
        self.main_layout.addWidget(self.labelLong)
        self.main_layout.addWidget(self.deleteBtn)

    def __delete(self):
        self.delete()
        self.ui.refresh()

    def delete(self):
        """
        Deletes the attribute. If the attribute has already been deleted then this will do
        nothing. This works by first unlocking the attribute, then breaking all connections going
        into and out of the attribute. Once this is done it is then deleted.
        """
        with UndoChunkContext():
            # Unlock the attribute
            cmds.setAttr(self.path, lock=False)

            # Break all connections to the attribute
            # in-coming connections
            incoming = cmds.listConnections(
                self.path, plugs=True, destination=False, source=True)
            if incoming:
                for c in incoming:
                    cmds.setAttr(c, lock=False)
                    cmds.disconnectAttr(c, self.path)

            # out-going connections
            outgoing = cmds.listConnections(
                self.path, plugs=True, destination=True, source=False)
            if outgoing:
                for c in outgoing:
                    cmds.setAttr(c, lock=False)
                    cmds.disconnectAttr(self.path, c)

            # Actually delete the attribute
            cmds.deleteAttr(self.path)

    def refresh(self):
        """
        Refreshes the display of this attribute. This should be called if the attribute's state
        has been changed at all.
        """
        style = "QWidget { padding: 5px 20px; } \
            #ShortName { background: %; border-radius: 3px } \
            #LongName { color: rgba(255, 255, 255, 0.5) } \
            #DeleteBtn { padding: 0; background: transparent; border: 0; }"
        if self.is_seperator():
            style = style.replace("%", "rgb(49, 167, 214)")
        elif self.is_hidden() and self.is_keyable() is False:
            style = style.replace("%", "rgb(51,51,51)")
        elif self.is_locked():
            style = style.replace("%", "rgb(89,104,117)")
        elif not self.is_keyable():
            style = style.replace("%", "rgb(148,148,148)")
        elif self.is_keyable():
            style = style.replace("%", "transparent")
        self.setStyleSheet(style)

    def rename(self, niceName=None, longName=None):
        """
        Renames the current attribute.

        niceName    str
            sets the new nice name for the attribute.

        longName    str
            sets the new long name for the attribute.
        """
        if niceName is not None:
            if cmds.attributeQuery(niceName, node=self.node, exists=True):
                return
            cmds.addAttr(self.path, edit=True, nn=niceName)

            # Here we do a quick rename of the attribute to force it's name being refreshed
            was_locked = self.is_locked()
            if was_locked:
                cmds.setAttr(self.path, lock=False)

            cmds.renameAttr(self.path, "TMP_" + self.longName)
            cmds.renameAttr("{}.{}".format(
                self.node, "TMP_" + self.longName), self.longName)

            if was_locked:
                cmds.setAttr(self.path, lock=True)

            self.niceName = niceName
            self.label.setText(niceName)

        if longName is not None:
            if cmds.attributeQuery(longName, node=self.node, exists=True):
                return

            was_locked = self.is_locked()
            if was_locked:
                cmds.setAttr(self.path, lock=False)

            cmds.renameAttr(self.path, longName)
            self.longName = longName
            self.labelLong.setText(longName)

            if was_locked:
                cmds.setAttr(self.path, lock=True)


class AttributeEditor(QDialog):

    def __init__(self, parent):
        super(AttributeEditor, self).__init__(parent=parent)

        # TODO create UI for editor

        # Get the currently selected attribute (default to max) and then insert a new attribute
        # with the given data type and settings.


class AttributeMasterAboutUI(QDialog):
    """
    Opens a dialog window to show details about this script and any important details
    that might be sueful for debugging or updates.
    """

    def __init__(self, parent, name="AttributeMasterAboutWindow"):
        deleteMayaWindowContext(name)
        super(AttributeMasterAboutUI).__init__(parent=parent)
        self.setObjectName(name)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle("Attribute Master - About")

        layout = QVBoxLayout()
        self.setLayout(layout)

        titleLabel = QLabel("About")
        versionLabel = QLabel("v" + __version__)

        infoText = QLabel("")

        author = QLabel("")
        date = QLabel("")
        github = QLabel('<a href="Woo">Link Test</a>')
        website = QLabel("")


class AttributeMaster(MayaQWidgetDockableMixin, QDialog):

    DISPLAY_LONGNAME = 0
    DISPLAY_VALUE = 1

    def __init__(self, parent=maya_main_window(), name=TOOL_NAME):
        deleteMayaWindowContext(name)
        super(AttributeMaster, self).__init__(parent)

        self.setObjectName(name)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(400, 500)
        self.displayState = AttributeMaster.DISPLAY_LONGNAME

        # This is a simple attribute to stop the closeEvent from being called
        self.window_is_open = False

    def run(self):
        self.create_ui()
        self.refresh()
        self.register_callback()

        # Set the state of thie tool to be open
        self.window_is_open = True

        # show the the tool window
        self.show(dockable=True)
        # self.raise_()

    def create_ui(self):
        """
        Creates all of the base UI elements for the attribute editor.
        """
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        spacer = QtWidgets.QSpacerItem(
            20, 40, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)

        # Create attribute view type

        title = QtWidgets.QHBoxLayout()
        self.titleLabel = QtWidgets.QLabel()
        title.addWidget(self.titleLabel)
        title.addSpacerItem(spacer)

        addSeperatorBtn = QtWidgets.QPushButton(
            "Seperator", icon=QtGui.QIcon(":/addClip.png"))
        addSeperatorBtn.clicked.connect(self.add_new_seperator)
        title.addWidget(addSeperatorBtn)

        addAttrBtn = QtWidgets.QPushButton(
            "Attribute", icon=QtGui.QIcon(":/addClip.png"))
        addAttrBtn.clicked.connect(self.add_attribute)
        title.addWidget(addAttrBtn)

        reloadBtn = QtWidgets.QPushButton(icon=QtGui.QIcon(":/refresh.png"))
        reloadBtn.clicked.connect(self.refresh)
        title.addWidget(reloadBtn)
        layout.addLayout(title)

        # Create the list view widget
        listWidget = QtWidgets.QListWidget()
        listWidget.setStyleSheet("\
            #AttributeList { background: rgba(40, 40, 40, 0.3); outline: none; border: 0; padding: 10px; border-radius: 10px } \
            QListWidget::item { border: 0; outline: none; border-radius: 5px; margin: 1px } \
            QListWidget::item:selected { background: rgba(24, 219, 148, 0.5); border: 0; outline: none; } \
        }")
        listWidget.setObjectName("AttributeList")
        listWidget.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollPerPixel)
        listWidget.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        layout.addWidget(listWidget)
        listWidget.setDragEnabled(True)
        listWidget.setDragDropMode(listWidget.InternalMove)
        listWidget.installEventFilter(self)
        listWidget.itemSelectionChanged.connect(self.on_selection_change)

        self.listWidget = listWidget

        # Create attribute info panel
        infoWidget = QtWidgets.QWidget()
        infoLayout = QtWidgets.QVBoxLayout()
        infoWidget.setLayout(infoLayout)

        nameLayout = QtWidgets.QFormLayout()
        self.niceNameInput = QtWidgets.QLineEdit()
        self.longNameInput = QtWidgets.QLineEdit()
        nameLayout.addRow(QtWidgets.QLabel("Nice Name"), self.niceNameInput)
        nameLayout.addRow(QtWidgets.QLabel("Long Name"), self.longNameInput)
        infoLayout.addLayout(nameLayout)

        validator = QtGui.QRegExpValidator(QtCore.QRegExp("\w+"))
        self.longNameInput.setValidator(validator)

        self.niceNameInput.returnPressed.connect(self.name_change_nice)
        self.longNameInput.returnPressed.connect(self.name_change_long)

        min = QtWidgets.QSpinBox()
        max = QtWidgets.QSpinBox()

        min.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                          QtWidgets.QSizePolicy.Fixed)
        max.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                          QtWidgets.QSizePolicy.Fixed)

        # keyable layout
        displayLayout = QtWidgets.QHBoxLayout()
        self.keyableBtn = QtWidgets.QRadioButton("Keyable")
        self.unkeyableBtn = QtWidgets.QRadioButton("Not Keyable")
        self.lockedBtn = QtWidgets.QRadioButton("Locked")
        self.hiddenBtn = QtWidgets.QRadioButton("Hidden")
        displayLayout.addWidget(self.keyableBtn)
        displayLayout.addWidget(self.unkeyableBtn)
        displayLayout.addWidget(self.lockedBtn)
        displayLayout.addWidget(self.hiddenBtn)
        infoLayout.addLayout(displayLayout)

        # Connect display click events
        self.keyableBtn.clicked.connect(self.set_keyable)
        self.unkeyableBtn.clicked.connect(self.set_notkeyable)
        self.lockedBtn.clicked.connect(self.set_displayable)
        self.hiddenBtn.clicked.connect(self.set_hidden)

        self.min = min
        self.max = max
        self.dataWidget = infoWidget

        layout.addWidget(infoWidget)

    def change_display_state(self, state):
        self.displayState = state

    @property
    def selected_attribute(self):
        item = self.listWidget.currentItem()
        return self.listWidget.itemWidget(item) if item is not None else None

    @property
    def selected_node(self):
        """
        Returns the currently selected node. If the selection has more than one item in it then it will
        awlays return the first selected node. If nothing is selected then None is returned.
        """
        selection = cmds.ls(sl=True)
        return selection[0] if len(selection) else None

    def set_keyable(self):
        selected = self.listWidget.selectedItems()
        if selected == None:
            return
        for item in selected:
            attr = self.listWidget.itemWidget(item)
            cmds.setAttr(attr.path, lock=False)
            cmds.setAttr(attr.path, keyable=True)
            attr.refresh()

    def set_notkeyable(self):
        selected = self.listWidget.selectedItems()
        if selected == None:
            return
        for item in selected:
            attr = self.listWidget.itemWidget(item)
            cmds.setAttr(attr.path, lock=False)
            cmds.setAttr(attr.path, keyable=False)
            cmds.setAttr(attr.path, channelBox=True)
            attr.refresh()

    def set_displayable(self):
        selected = self.listWidget.selectedItems()
        if selected == None:
            return
        for item in selected:
            attr = self.listWidget.itemWidget(item)
            cmds.setAttr(attr.path, lock=True)
            cmds.setAttr(attr.path, keyable=False)
            cmds.setAttr(attr.path, channelBox=True)
            attr.refresh()

    def set_hidden(self):
        selected = self.listWidget.selectedItems()
        if selected == None:
            return
        for item in selected:
            attr = self.listWidget.itemWidget(item)
            cmds.setAttr(attr.path, keyable=False)
            cmds.setAttr(attr.path, lock=True)
            cmds.setAttr(attr.path, channelBox=False)
            attr.refresh()

    def name_change_long(self):
        self.name_change(type='long')

    def name_change_nice(self):
        self.name_change(type='nice')

    def name_change(self, type):
        """
        Updates the currently selected attributes name.
        """

        attr = self.selected_attribute
        if attr == None:
            return

        if type == 'nice':
            attr.rename(niceName=self.niceNameInput.text())
        if type == 'long':
            attr.rename(longName=self.longNameInput.text())

    def eventFilter(self, sender, event):
        if (event.type() == QtCore.QEvent.ChildRemoved):
            # Item was moved
            self.reorder()
        return False

    def on_selection_change(self):
        """
        Called when the selection is changed in the attribute list.
        """
        sel_size = len(self.listWidget.selectedItems())
        ordered = self.attributes_ordered
        attr = ordered[self.listWidget.currentRow()] if len(ordered) else None
        self.dataWidget.setEnabled(attr is not None)

        self.longNameInput.setText(
            attr.longName if attr and sel_size < 2 else "")
        self.niceNameInput.setText(
            attr.niceName if attr and sel_size < 2 else "")

        if sel_size > 1:
            self.longNameInput.setEnabled(False)
            self.niceNameInput.setEnabled(False)
        else:
            self.longNameInput.setEnabled(True)
            self.niceNameInput.setEnabled(True)

        if attr is not None:
            self.max.setValue(attr.max[0] if attr and attr.hasMax else 0)
            self.max.setEnabled(attr is not None and attr.hasMax)
            self.min.setValue(attr.min[0] if attr and attr.hasMin else 0)
            self.min.setEnabled(attr is not None and attr.hasMin)

            self.keyableBtn.setChecked(attr.is_keyable())
            self.unkeyableBtn.setChecked(attr.is_keyable() is False)
            self.lockedBtn.setChecked(attr.is_locked())
            self.hiddenBtn.setChecked(
                attr.is_hidden() and attr.is_keyable() is False)
        return True

    def refresh(self, event=None, *args, **kwargs):
        """
        Refreshes the tool.
        """
        self.listWidget.clear()

        selection = cmds.ls(sl=True)
        title = selection[0] if len(selection) else "Nothing Selected"
        self.titleLabel.setText("<h2>{}</h2>".format(title))
        self.dataWidget.setVisible(len(selection))
        self.dataWidget.setEnabled(self.listWidget.currentRow() > 0)

        self.on_selection_change()

        if len(selection) == 0:
            return

        select = selection[0]
        user_attributes = cmds.listAttr(select, userDefined=True)

        if user_attributes is None:
            return

        for x in user_attributes:
            niceName = cmds.attributeQuery(x, node=select, nn=True)
            longName = cmds.attributeQuery(x, node=select, ln=True)
            keyable = cmds.attributeQuery(x, node=select, k=True)
            channelBox = cmds.attributeQuery(x, node=select, channelBox=True)
            hasMax = cmds.attributeQuery(x, node=select, maxExists=True)
            hasMin = cmds.attributeQuery(x, node=select, minExists=True)
            type = cmds.attributeQuery(x, node=select, attributeType=True)

            attr = Attribute(self, select, niceName, longName=longName,
                             keyable=keyable, channelBox=channelBox, type=type)

            item = QtWidgets.QListWidgetItem()
            self.listWidget.insertItem(self.listWidget.count(), item)
            self.listWidget.setItemWidget(item, attr)
            item.setSizeHint(attr.sizeHint())

    @property
    def attributes_ordered(self):
        """
        Returns a property containing all of the attributes listed in their correct order.

        :return: str[]
        """
        ordered = []
        for index in range(self.listWidget.count()):
            item = self.listWidget.item(index)
            widget = self.listWidget.itemWidget(item)
            if widget is not None:
                ordered.append(widget)
        return ordered

    def reorder(self):
        """
        Reorders all the attributes of the node by dleteting them in the order of the list, and
        then undoing it in a way that adds them in a matching order.
        """
        with UndoStateContext():
            for attribute in reversed(self.attributes_ordered):
                attribute.delete()

            for _ in range(self.listWidget.count()):
                cmds.undo()

    def add_new_seperator(self):
        """
        Adds a new seperator attribute. A seperator attribute is simplt there
        to act as a title or way ot seperating out the content into 'catagories'
        for easier viewing in the channel box.
        """
        node = self.selected_node
        if node is None:
            return

        # find the next aviliabe id for a seperator
        id = 0
        max = 0
        while cmds.attributeQuery(("__seperator_" + str(id)), node=node, exists=True):
            max += 1
            if max > 10:
                break
            id += 1

        name = "__seperator_" + str(id)

        text, result = QtWidgets.QInputDialog.getText(
            self, "Add Seperator", "Seperator Name:")

        if result and len(text) > 0:
            cmds.addAttr(node, longName=name, attributeType='enum',
                         niceName=text, enumName=" ")
            cmds.setAttr("{}.{}".format(node, name), channelBox=True)
            cmds.setAttr("{}.{}".format(node, name), lock=True)
            self.refresh()

    def add_attribute(self):
        """
        Otions the attribute creator to add a new attribute to the currently selected node.
        """
        if self.selected_node is None:
            return
        try:
            import maya.mel as mel
            mel.eval("dynAddAttrWin( {} )")
        except:
            pass

    def remove_attribute(self):
        pass

    def register_callback(self):
        """
        Registers the callback method used for when the selection of objects is changed in the scene.
        """
        self.callback = OpenMaya.MModelMessage.addCallback(
            OpenMaya.MModelMessage.kActiveListModified,
            self.refresh
        )

    def remove_callback(self):
        """
        Removes the callback if it has been added for handling selection changes in the scene.
        """
        if self.callback is not None:
            OpenMaya.MModelMessage.removeCallback(self.callback)

    def dockCloseEventTriggered(self):
        # Geto workaround to get the closeEvent being called to unhook callbacks
        self.closeEvent(None)

    def closeEvent(self, event):
        if not self.window_is_open:
            return
        self.window_is_open = False
        self.remove_callback()
        super(AttributeMaster, self).closeEvent(event)


def attributeMaster():
    AttributeMaster().run()


attributeMaster()

# mel.createMelWrapper(attributeMaster)
