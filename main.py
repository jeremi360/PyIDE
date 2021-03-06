# Had to install libgtksourceview-3.0-dev
# Will need pygit2 (python3-pygit2) for git integration

import gi, os, sys, subprocess, re, json, pygit2, signal, psutil, stat
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkSource', '3.0')
gi.require_version('WebKit', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk, Gdk,GtkSource, Vte, GLib, WebKit, Pango
from gi.repository.GdkPixbuf import Pixbuf
from os import listdir
from os.path import isfile, join
from pygit2 import Repository
from compiler import Compiler
from modules.autoBracket import AutoBracket
from modules.autoComplete import GediPlugin
from modules.linter import Linter

wW = __import__('welcomeWindow')

def isTextFile(fn):
    msg = subprocess.Popen(["file", fn], stdout=subprocess.PIPE).communicate()[0]
    return 'text' in str(msg) or 'source' in str(msg)

def isImageFile(fn):
    msg = subprocess.Popen(["file", fn], stdout=subprocess.PIPE).communicate()[0]
    return 'image' in str(msg)

def nth_split(s, delim, n):
    p, c = -1, 0
    while c < n:
        p = s.index(delim, p + 1)
        c += 1
    return s[:p], s[p + 1:]

def human_format(num):
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    # add more suffixes if you need them
    res = '%.2f%s' % (num, ['', 'K', 'M', 'G', 'T', 'P'][magnitude])
    if res.split('.')[1][0:len(res.split('.')[1])-1] == '00':
        res = res.replace('.00', '')
    elif res.split('.')[1][1:len(res.split('.')[1])-1] == '0':
        res = res[:len(res) - 2] + res[(len(res)-1):]
    elif res[len(res) - 2:] == '00':
        res = res.replace('.00', '')
    return res

class IDEWindow(Gtk.Window):
    """docstring for IDEWindow."""
    def __init__(self, openPath):
        super(IDEWindow, self).__init__()

        ## Win General

        self.set_title('IDE')
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(1000, 500)
        # i = Gtk.Image.new_from_icon_name('document-edit-symbolic', Gtk.IconSize.MENU)
        self.set_default_icon_name('document-edit-symbolic')
        #self.set_border_width(10)
        self.connect('delete-event', self._quit)

        ### Win Accels

        accel = Gtk.AccelGroup()
        accel.connect(Gdk.keyval_from_name('s'), Gdk.ModifierType.CONTROL_MASK, 0, self.saveFile)
        accel.connect(Gdk.keyval_from_name('b'), Gdk.ModifierType.CONTROL_MASK, 0, self.compile)
        accel.connect(Gdk.keyval_from_name('f'), Gdk.ModifierType.CONTROL_MASK, 0, self.toggleSearch)
        # accel.connect(16777215, Gdk.ModifierType.SHIFT_MASK, 0, self.bracketComplete)
        #accel.connect(Gdk.keyval_from_name('p'), Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK, 0, self.command) #future Ctrl + Shift + P command popup
        self.add_accel_group(accel)

        ## Editor General

        self.projectPath = None
        self.projectName = None
        self.curFileName = None
        self.curFileIndex = None
        self.curLanguage = None
        self.curSettings = None
        self.files = []
        self.tempFilesText = []
        self.langs = []
        self.compilerOptions = []
        self.running = False
        self.runningProccess = None

        self.filesObject = []
        self.comp = None

        self.waitingForBracketCompletion = False
        self.autoToggling = False
        ## Header Bar

        self.hb = Gtk.HeaderBar()

        # system-run = engine icon, media-playback-start = red play icon, gtk-media-play = white play
        self.compileBtn = Gtk.Button.new_from_icon_name('media-playback-start-symbolic', Gtk.IconSize.MENU)
        self.compileBtn.set_tooltip_text('Compile + Run')
        self.compileBtn.connect('clicked', self.compile)
        # self.compileBtn.set_sensitive(False)

        self.terminalBtn = Gtk.Button.new_from_icon_name('utilities-terminal-symbolic', Gtk.IconSize.MENU)
        self.terminalBtn.set_tooltip_text('Toggle terminal')
        self.terminalBtn.connect('clicked', self.toggleTerminal)

        ### Creating popup menu

        self.settingsBtn = Gtk.Button.new_from_icon_name('view-more-symbolic', Gtk.IconSize.MENU)
        self.settingsBtn.connect('clicked', self.onSettingsBtnClick)

        self.settingsPopover = Gtk.Popover()

        self.settingsList = Gtk.ListBox()

        r = Gtk.ListBoxRow()
        a = Gtk.CheckButton()
        a.set_label('Toggle Dark Mode')
        self.toggleDarkCheck = a
        self.toggleDarkCheck.connect('toggled', self.onToggleDark)
        r.add(a)
        r.set_margin_left(5)
        r.set_margin_right(5)
        r.set_margin_top(5)
        self.settingsList.insert(r, -1)

        r = Gtk.ListBoxRow()
        a = Gtk.CheckButton()
        a.set_label('Highlight Matching Brackets')
        self.toggleHighlightCheck = a
        self.toggleHighlightCheck.connect('toggled', self.onToggleHighlight)
        r.add(a)
        r.set_margin_left(5)
        r.set_margin_right(5)
        self.settingsList.insert(r, -1)

        r = Gtk.ListBoxRow()
        a = Gtk.CheckButton()
        a.set_label('Show Line Numbers')
        self.toggleLineCheck = a
        self.toggleLineCheck.connect('toggled', self.onToggleLine)
        r.add(a)
        r.set_margin_left(5)
        r.set_margin_right(5)
        self.settingsList.insert(r, -1)

        r = Gtk.ListBoxRow()
        a = Gtk.CheckButton()
        a.set_label('Word Wrap')
        self.toggleWordWrap = a
        self.toggleWordWrap.connect('toggled', self.onToggleWrap)
        r.add(a)
        r.set_margin_left(5)
        r.set_margin_right(5)
        self.settingsList.insert(r, -1)
        
        r = Gtk.ListBoxRow()
        _hb = Gtk.HBox()
        _hb.get_style_context().add_class('linked')
        self.styleChooserButton = GtkSource.StyleSchemeChooserButton()
        self.applyStyleButton = Gtk.Button.new_from_icon_name('emblem-ok-symbolic', Gtk.IconSize.MENU)
        self.applyStyleButton.connect('clicked', self.applyStyle)
        _hb.pack_start(self.styleChooserButton, True, True, 0)
        _hb.pack_start(self.applyStyleButton, True, True, 0)
        r.add(_hb)
        r.set_margin_left(5)
        r.set_margin_right(5)
        r.set_margin_bottom(5)
        self.settingsList.insert(r, -1)
        

        r = Gtk.ListBoxRow()
        _hb = Gtk.HBox()
        btn = Gtk.Button.new_from_icon_name('system-run-symbolic', Gtk.IconSize.MENU)
        btn.set_tooltip_text('Build Project')
        _hb.pack_start(btn, True, True, 0)
        btn = Gtk.Button.new_from_icon_name('media-playback-start-symbolic', Gtk.IconSize.MENU)
        btn.set_tooltip_text('Run Project')
        _hb.pack_start(btn, True, True, 0)
        btn = Gtk.Button.new_from_icon_name('document-edit-symbolic', Gtk.IconSize.MENU)
        btn.set_tooltip_text('Edit Project')
        _hb.pack_start(btn, True, True, 0)

        _hb.get_style_context().add_class('linked')
        r.add(_hb)
        r.set_margin_left(5)
        r.set_margin_right(5)
        r.set_margin_bottom(5)
        self.settingsList.insert(r, -1)

        # bx = Gtk.VBox()
        # bx.pack_start(self.settingsList, False, False, 0)
        # bx.set_border_width(10)

        self.settingsList.set_selection_mode(Gtk.SelectionMode.NONE)

        self.settingsPopover.add(self.settingsList)
        self.settingsPopover.set_relative_to(self.settingsBtn)

        self.hb.pack_end(self.settingsBtn)

        #self.folderBtn = Gtk.Button.new_from_icon_name('folder-new', Gtk.IconSize.MENU)
        #self.folderBtn.set_tooltip_text('Open Project Folder')
        #self.folderBtn.connect('clicked', self.openProject)
        #self.hb.pack_start(self.folderBtn)

        ########################################
        bx = Gtk.HBox()
        bx.get_style_context().add_class('linked')
        bx.pack_start(self.compileBtn, False, False, 0)
        self.stateEntry = Gtk.Entry()
        self.stateEntry.set_sensitive(False)
        self.stateEntry.set_text('Loaded')
        bx.pack_start(self.stateEntry, False, False, 0)
        self.hb.pack_start(bx)
        #self.hb.pack_start(self.terminalBtn)
        ########################################

        self.hb.set_title('Py IDE')
        self.hb.set_show_close_button(True)

        #self.hb.pack_end(self.searchEntry)

        ## Views And Buffers

        self.sview = GtkSource.View()
        self.stable = Gtk.TextTagTable()
        self.sbuff = GtkSource.Buffer.new(self.stable)
        self.found_tag = self.sbuff.create_tag('found-tag', background='rgba(200,200,200,.8)')
        self.error_tag = self.sbuff.create_tag('error-tag', underline=Pango.Underline.ERROR)
        self.lmngr = GtkSource.LanguageManager()
        self.sviewScroll = Gtk.ScrolledWindow()
        self.sviewBox = Gtk.HBox()
        self.smap = GtkSource.Map()

        self.smap.set_view(self.sview)

        self.sview.set_auto_indent(True)
        self.sview.set_buffer(self.sbuff)
        self.sview.set_indent_on_tab(True)
        self.sview.set_insert_spaces_instead_of_tabs(False)
        self.sview.set_left_margin(10)
        self.sview.set_property('smart-home-end', GtkSource.SmartHomeEndType.ALWAYS)
        self.sview.set_smart_backspace(True)
        font = Pango.FontDescription('Monospace 10')
        self.sview.modify_font(font)
        # self.sview.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.sview.set_tab_width(8)
        # self.sview.set_hscroll_policy(Gtk.ScrollablePolicy.MINIMAL)
        # self.sview.set_draw_spaces(GtkSource.DrawSpacesFlags.TAB)
        self.sbuff.connect('insert-text', self.onTextInsert)
        self.sbuff.connect('changed', self.onTextChanged)
        # self.sbuff.set_style_scheme(GtkSource.StyleScheme.get_style('tango'))
        #self.sview.set_pixels_above_lines(5)

        ### Testing completion

        self.sview_completion = self.sview.get_completion()
        self.sview_completion.set_property('remember-info-visibility', True)
        self.sview_completion.set_property('auto-complete-delay', 0)
        self.sview_provider = GtkSource.CompletionWords.new('PyIDE Completion 2', self.getPix('folder'))
        self.sview_provider.register(self.sbuff)
        self.sview_completion.add_provider(self.sview_provider)
        # provider = GtkSource.CompletionWords.new('PyIDE Completion 2')
        # context = GtkSource.CompletionContext()
        # context.add_proposals(provider, [GtkSource.CompletionItem(label='class', text='class', icon=self.getPix('insert-object-symbolic'), info='Define a class')], True)
        # self.sview_completion.add_provider(provider)

        ## TreeView

        self.treeView = None # Turn this into a Gtk.TreeView(self.fileStore) when fileStore has something
        self.fileList = []
        self.fileStore = None # Turn this into a Gtk.ListStore (lists that TreeView can display)

        ## Lines

        self.lines = Gtk.Button('0 Lines')

        self.linesPopover = Gtk.Popover()
        self.linesPopover.set_relative_to(self.lines)

        vb = Gtk.VBox()
        a = Gtk.Label('Lines: ')
        self.linesLbl = a
        vb.pack_start(a, True, True, 0)
        a = Gtk.Label('Chars: ')
        self.charsLbl = a
        vb.pack_start(a, True, True, 0)
        a = Gtk.Label('Language: ')
        self.languageLbl = a
        vb.pack_start(a, True, True, 0)
        vb.set_border_width(10)

        self.linesPopover.add(vb)

        self.lines.connect('clicked', self.onLinesCliked)

        ##

        hb = Gtk.HBox()
        hb.get_style_context().add_class('linked')
        self.sideNewFileBtn = Gtk.Button.new_from_icon_name('document-new-symbolic', Gtk.IconSize.MENU)
        self.sideNewFileBtn.connect('clicked', self.createNewFile)
        self.sideNewFolderBtn = Gtk.Button.new_from_icon_name('folder-new-symbolic', Gtk.IconSize.MENU)
        self.sideNewFolderBtn.connect('clicked', self.createNewFolder)
        hb.pack_start(self.sideNewFileBtn, False, False, 0)
        hb.pack_start(self.sideNewFolderBtn, False, False, 0)

        hb.pack_end(self.terminalBtn, False, False, 0)
        hb.pack_start(self.lines, True, True, 0)

        self.pane = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        self.pane.set_wide_handle(False)
        self.terminalPane = Gtk.Paned.new(Gtk.Orientation.VERTICAL)
        #self.terminalPane.set_wide_handle(True)

        self.terminal = Vte.Terminal()

        self.sideVBox = Gtk.VBox()
        self.sideVBox.pack_end(hb, False, False, 0)

        self.sideView = Gtk.ListBox()
        self.sideView.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sideView.set_activate_on_single_click(True)
        self.sideView.connect('row-selected', self.handleSideClick)
        self.sideScroller = Gtk.ScrolledWindow()
        #self.sideScroller.add(self.sideView)
        # self.sideScroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.sideVBox.pack_start(self.sideScroller, True, True, 0)

        # MD Preview

        self.mdPreviewer = WebKit.WebView()
        self.mdPreviewer.load_uri('file://' + os.path.dirname(os.path.abspath(__file__)) + '/browser/index.html')

        #####################################

        self.searchToolbar = Gtk.Revealer()
        self.searchToolbar.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.searchToolbar.set_transition_duration(300)

        self.searchEntry = Gtk.Entry()
        self.searchEntry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, 'preferences-system-search-symbolic')
        self.searchEntry.connect('changed', self.find)
        self.searchEntry.set_width_chars(50)

        self.searchFindButton = Gtk.Button('Find')
        self.searchFindButton.connect('clicked', self.find)

        self.searchCloseButton = Gtk.Button.new_from_icon_name('window-close-symbolic', Gtk.IconSize.MENU)
        self.searchCloseButton.connect('clicked', self.toggleSearch)

        self.searchVBox = Gtk.HBox()

        bx = Gtk.HBox()
        bx.pack_start(self.searchEntry, False, False, 0)
        bx.pack_start(self.searchFindButton, False, False, 0)
        bx.set_halign(Gtk.Align.CENTER)
        

        self.searchVBox.add(bx)
        self.searchVBox.pack_end(self.searchCloseButton, False, False, 0)

        self.searchToolbar.add(self.searchVBox)
        self.searchToolbar.set_reveal_child(False)

        #####################################

        # SVIEWSCROLL EVENTS

        #self.sviewScroll.connect('event-after', self.sviewScrollEvents)

        #self.sviewScroll.connect('scroll-child', self.updateMinimap)
        self.sviewScroll.add(self.sview)
        self.sviewBox.pack_start(self.sviewScroll, True, True, 0)

        self.sviewBox.pack_start(self.smap, False, False, 0)

        ##########################################

        self.searchPane = Gtk.VBox()

        self.sviewPaned = Gtk.Paned()
        self.sviewPaned.pack1(self.sviewBox, False, False)
        self.sviewPaned.pack2(self.mdPreviewer)

        self.pane.pack1(self.sideVBox, False, False)

        self.terminalPane.pack1(self.sviewPaned, True, True) ##################
        self.terminalPane.add2(self.terminal)

        self.searchPane.pack_start(self.searchToolbar, False, False, 0)
        self.searchPane.pack_start(self.terminalPane, True, True, 0)

        self.pane.add2(self.searchPane)

        self.add(self.pane)
        self.set_titlebar(self.hb)

        self.loadSettings()

        self.show_all()

        self.openProject(openPath)
        self.sviewPaned.get_child2().hide()

        ## Appending modules

        self.modules = []

        self.autoBracket = AutoBracket(self)
        self.modules.append(self.autoBracket)
        self.autoComplete = GediPlugin(self)
        self.modules.append(self.autoComplete)
        self.linter = Linter(self)
        self.modules.append(self.linter)

        for module in self.modules:
            module.do_activate()

        Gtk.main()

    def getPix(self, iconName):
        return Gtk.Image.new_from_icon_name(iconName, Gtk.IconSize.MENU).get_pixbuf()

    def onToggleWrap(self, *args):
        if self.autoToggling:
            return
        self.wordWrap = self.toggleWordWrap.get_active()
        self.saveSettings()
        self.applySettings()

    def sviewScrollEvents(self, widget, event):
        if event.type != Gdk.EventType.SCROLL:
            return

        # print('update')
        # self.smap.show_all()

    def openTerminal(self, *args):
        self.terminal.show()

    def _quit(self, *args):
        if len(self.filesObject) > 0:
            unsaved = False
            unsavedFile = ''
            for i,f in enumerate(self.filesObject):
                if not f['curText'] == f['originalText']:
                    unsaved = True
                    unsavedFile = os.path.basename(f['path'])
                    break

            if unsaved:
                res = self.confirm('{} is not saved, are you sure you want to exit without saving?'.format(os.path.basename(f['path'])))
                if res:
                    self.linter.do_deactivate()
                    Gtk.main_quit()
                else:
                    return True
            else:
                self.linter.do_deactivate()
                Gtk.main_quit()

        else:
            self.linter.do_deactivate()
            Gtk.main_quit()
            
    def applyStyle(self, *args):
        self.sbuff.set_style_scheme(self.styleChooserButton.get_style_scheme())

    def find(self, *args):

        self.sbuff.remove_tag(self.found_tag, self.sbuff.get_start_iter(), self.sbuff.get_end_iter())
        text = self.searchEntry.get_text()
        start = self.sbuff.get_start_iter()
        

        self.markFound(text, start)

    
    def markFound(self, text, start):
        end = self.sbuff.get_end_iter()

        match = start.forward_search(text, 0, end)

        if match != None:
            match_start, match_end = match
            self.sbuff.apply_tag(self.found_tag, match_start, match_end)
            self.markFound(text, match_end)


    def onToggleDark(self, *args):
        if self.autoToggling:
            return
        self.darkMode = not self.darkMode
        self.saveSettings()
        self.applySettings()

    def onLinesCliked(self, *args):
        ##
        self.linesPopover.show_all()

    def saveSettings(self, *args):
        ##
        _settings = {
            'highlight-matching-brackets': self.highlightMatchingBrackets,
            'show-line-numbers': self.showLineNumbers,
            'word-wrap': self.wordWrap,
            'dark-mode': self.darkMode
        }

        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pyide-settings.json'), 'w+') as f:
            json.dump(_settings, f, indent=4, sort_keys=True, separators=(',', ':'))

    def onToggleLine(self, *args):
        ##
        if self.autoToggling:
            return
        self.showLineNumbers = self.toggleLineCheck.get_active()
        self.saveSettings()
        self.applySettings()

    def onToggleHighlight(self, *args):
        ##
        if self.autoToggling:
            return
        self.highlightMatchingBrackets = self.toggleHighlightCheck.get_active()
        self.saveSettings()
        self.applySettings()

    def onTextChanged(self, *args):
        txt = ''
        if self.sbuff.get_line_count() > 1 or self.sbuff.get_line_count() == 0:
            txt = ' Lines'
        else:
            txt = ' Line'
        self.lines.set_label(str(human_format(self.sbuff.get_line_count())) + txt)
        self.linesLbl.set_text('Lines: {}'.format(self.sbuff.get_line_count()))
        self.charsLbl.set_text('Chars: {}'.format(str(self.sbuff.get_char_count())))

        self.filesObject[self.curFileIndex]['curText'] = self.getCurrentText()

    def onTextInsert(self, buff, location, text, len):
        if text == '(':
            self.waitingForBracketCompletion = True

    def toggleTerminal(self, *args):
        if self.terminal.props.visible:
            self.terminal.hide()
        else:
            self.terminal.show()

    def toggleSearch(self, *args):
        self.searchToolbar.set_reveal_child(not self.searchToolbar.get_reveal_child())
        if self.searchToolbar.get_reveal_child():
            self.searchEntry.grab_focus()
        else:
            self.sbuff.remove_tag(self.found_tag, self.sbuff.get_start_iter(), self.sbuff.get_end_iter())
            self.sview.grab_focus()

    def onSettingsBtnClick(self, *args):
        self.settingsPopover.show_all()

    def bracketComplete(self, *args):
    	print(')')

    def loadSettings(self, *args):

        defaultSettings = {'highlight-matching-brackets': True,'show-line-numbers': True,'word-wrap': True, 'dark-mode': False}

        curSettings = None

        if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pyide-settings.json')):
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pyide-settings.json'), 'r') as f:
                curSettings = json.load(f)
        else:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pyide-settings.json'), 'w+') as f:
                json.dump(defaultSettings, f, indent=4, sort_keys=True, separators=(',', ':'))
                curSettings = defaultSettings

        self.curSettings = curSettings

        self.highlightMatchingBrackets = curSettings['highlight-matching-brackets']
        self.showLineNumbers = curSettings['show-line-numbers']
        self.wordWrap = curSettings['word-wrap']
        self.darkMode = curSettings['dark-mode']

        self.applySettings()

    def applySettings(self, *args):
        self.sview.set_show_line_numbers(self.showLineNumbers)
        self.sbuff.set_highlight_matching_brackets(self.highlightMatchingBrackets)

        if self.wordWrap:
            self.sview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        else:
            self.sview.set_wrap_mode(Gtk.WrapMode.NONE)

        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', self.darkMode)

        self.autoToggling = True

        self.toggleDarkCheck.set_active(self.darkMode)
        self.toggleHighlightCheck.set_active(self.highlightMatchingBrackets)
        self.toggleLineCheck.set_active(self.showLineNumbers)
        self.toggleWordWrap.set_active(self.wordWrap)

        self.autoToggling = False

        self.terminal.set_color_background(self.sview.get_style_context().get_background_color(Gtk.StateFlags.NORMAL))

        if hasattr(self, 'gitButton'):
            text = Repository(self.projectPath).head.shorthand
            repo = Gtk.HBox(spacing=6)
            img = None
            if self.darkMode:
                img = Gtk.Image.new_from_file('resources/icons/git-branch-white.svg')
            else:
                img = Gtk.Image.new_from_file('resources/icons/git-branch.svg')
            repo.pack_start(img, False, False, 0)
            repo.pack_start(Gtk.Label(text), False, False, 0)
            repo.show_all()

            self.gitButton.remove(self.gitButton.get_child())
            self.gitButton.set_tooltip_text("On branch " + text)
            self.gitButton.add(repo)

    def is_exe(self, fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    def getCurrentText(self, *args):
        return self.sbuff.get_text(self.sbuff.get_start_iter(), self.sbuff.get_end_iter(), False)

    def saveOnChangeFile(self, *args):
        self.tempFilesText[self.curFileIndex] = self.getCurrentText()
        #print("Saved on change, {}".format(self.curFileIndex))

    def handleSideClick(self, *args):

        # This corrects the "AttributeError: 'NoneType' object has no attribute 'get_index'" error on close
        if self.sideView.get_selected_row() is None:
            return

        if isImageFile(self.projectPath + '/' + self.files[self.sideView.get_selected_row().get_index()]):
            os.system('xdg-open ' + self.projectPath + '/' + self.files[self.sideView.get_selected_row().get_index()])
            return

        if not isTextFile(self.projectPath + '/' + self.files[self.sideView.get_selected_row().get_index()]):
            print('Not text')
            return

        if type(self.curFileIndex) is int:
            self.saveOnChangeFile()

        row = self.sideView.get_selected_row()
        selected = row.get_index()
        #print(selected)
        self.curFileIndex = selected
        self.curFileName = self.files[selected]

        if type(self.tempFilesText[self.curFileIndex]) is not str:
            self.openFile(self.projectPath + '/' + self.files[selected])
        else:
            self.openFileFromTemp()

        self.languageLbl.set_text('Language: {}'.format(self.sbuff.get_language().get_name()))

    def openProject(self, __file=None, *args):

            ## Check if given project path is really a path, if so set it as self.projectPath

            if os.path.isdir(__file):
                self.projectPath = os.path.abspath(__file)
                self.projectName = self.projectPath.split('/')[len(self.projectPath.split('/')) - 1]
            else:
                print("{} is not a directory!".format(__file))
                sys.exit()

            self.hb.set_title('PyIDE - ' + self.projectName)
            self.hb.set_subtitle(self.projectPath)

            ####################################################################

            # initialize the filesystem treestore
            fileSystemTreeStore = Gtk.TreeStore(str, Pixbuf, str)
            # populate the tree store
            self.populateFileSystemTreeStore(fileSystemTreeStore, self.projectPath)
            # initialize the TreeView
            fileSystemTreeView = Gtk.TreeView(fileSystemTreeStore)
            fileSystemTreeView.set_property('activate-on-single-click', True)
            fileSystemTreeView.set_property('show-expanders', True)
            fileSystemTreeView.set_property('enable-search', True)




            # Create a TreeViewColumn
            treeViewCol = Gtk.TreeViewColumn(self.projectName)
            # Create a column cell to display text
            colCellText = Gtk.CellRendererText()
            # Create a column cell to display an image
            colCellImg = Gtk.CellRendererPixbuf()
            # Add the cells to the column
            treeViewCol.pack_start(colCellImg, False)
            treeViewCol.pack_start(colCellText, True)
            # Bind the text cell to column 0 of the tree's model
            treeViewCol.add_attribute(colCellText, "text", 0)
            # Bind the image cell to column 1 of the tree's model
            treeViewCol.add_attribute(colCellImg, "pixbuf", 1)
            # Append the columns to the TreeView
            fileSystemTreeView.append_column(treeViewCol)
            # add "on expand" callback
            fileSystemTreeView.connect("row-expanded", self.onRowExpanded)
            # add "on collapse" callback
            fileSystemTreeView.connect("row-collapsed", self.onRowCollapsed)


            # add "on row selected" callback
            self.selectedRow = fileSystemTreeView.get_selection()
            self.selectedRow.connect('changed', self.onRowActivated)

            scrollView = Gtk.ScrolledWindow()
            # scrollView.add(fileSystemTreeView)

            if len(self.sideScroller.get_children()) >= 1:
                self.sideScroller.remove(self.sideScroller.get_child())
                print('removed')

            self.sideScroller.add(fileSystemTreeView)
            self.sideScroller.show_all()

            # if len(self.compilerOptions) >= 1:
            #     self.compileBtn.set_sensitive(True)

            curShell = os.environ.get('SHELL')

            self.terminal.set_color_background(self.sview.get_style_context().get_background_color(Gtk.StateFlags.NORMAL))
            self.terminal.spawn_sync(
                    Vte.PtyFlags.DEFAULT, #default is fine
                    self.projectPath, #where to start the command?
                    [curShell], #where is the emulator?
                    [], #it's ok to leave this list empty
                    GLib.SpawnFlags.DO_NOT_REAP_CHILD,
                    None, #at least None is required
                    None,
                    )
            self.terminal.hide()

            if hasattr(self, 'gitButton'):
                self.hb.remove(self.gitButton)

            self.gitButton = Gtk.Button()
            self.hb.pack_end(self.gitButton)

            if os.path.isdir(self.projectPath + '/.git'):
                text = Repository(self.projectPath).head.shorthand
                repo = Gtk.HBox(spacing=6)
                img = None
                if self.darkMode:
                    img = Gtk.Image.new_from_file('resources/icons/git-branch-white.svg')
                else:
                    img = Gtk.Image.new_from_file('resources/icons/git-branch.svg')
                repo.pack_start(img, False, False, 0)
                repo.pack_start(Gtk.Label(text), False, False, 0)
                repo.show_all()

                if len(self.gitButton) >= 1:
                    self.gitButton.remove(self.gitButton.get_child())

                self.gitButton.add(repo)
                self.gitButton.show_all()
                self.gitButton.set_tooltip_text("On branch " + text)

            else:
                self.gitButton.hide()

    def updateMinimap(self, *args):
        self.smap.show_all()
        print('update minimap')

    def onRowActivated(self, selection):
        # print(path.to_string()) # Might do the job...
        model, row = selection.get_selected()
        if row is not None:
            # print(model[row][0])
            path = model.get_path(row).to_string()
            pathArr = path.split(':')
            fileFullPath = ''

            if len(pathArr) <= 1:
                if not os.path.isdir(os.path.realpath(os.path.join(self.projectPath, model[row][0]))):
                    self.openFile(os.path.realpath(os.path.join(self.projectPath, model[row][0])))
                    self.autoComplete.on_document_load()
                    self.linter.on_document_load()
                else:
                    exp = self.sideScroller.get_child().row_expanded(model.get_path(row))
                    if not exp:
                        self.sideScroller.get_child().expand_row(model.get_path(row), False)
                    else:
                        self.sideScroller.get_child().collapse_row(model.get_path(row))

            else:
                # print(row)
                # print(model)
                # print(model.iter_depth(row))

                p = model[row][0] # LAST ITEM IN PATH

                i = model.iter_depth(row)
                j = i
                cur = None
                while j > 0: # FOR EACH PARENT ADD THE LAST TO p
                    cur = model.iter_parent(cur) if not cur is None else model.iter_parent(row)
                    p = model[cur][0] + '/' + p # p = LAST PARENT + '/' + p
                    j -= 1

                if not os.path.isdir(os.path.realpath(os.path.join(self.projectPath, p))):
                    self.openFile(os.path.realpath(os.path.join(self.projectPath, p)))
                    self.autoComplete.on_document_load()
                    self.linter.on_document_load()
                else:
                    exp = self.sideScroller.get_child().row_expanded(model.get_path(row))
                    if not exp:
                        self.sideScroller.get_child().expand_row(model.get_path(row), False)
                    else:
                        self.sideScroller.get_child().collapse_row(model.get_path(row))

            self.languageLbl.set_text('Language: {}'.format(self.sbuff.get_language().get_name() if not self.sbuff.get_language() is None else "Plain"))


        else:
            print('None')

    def populateFileSystemTreeStore(self, treeStore, path, parent=None):
        itemCounter = 0
        # iterate over the items in the path
        _list = os.listdir(path)
        _list.sort(key=str.lower)
        for item in _list:
            # Get the absolute path of the item
            itemFullname = os.path.join(path, item)
            # Extract metadata from the item
            itemMetaData = os.stat(itemFullname)
            # Determine if the item is a folder
            itemIsFolder = stat.S_ISDIR(itemMetaData.st_mode)
            # Generate an icon from the default icon theme
            itemIcon = None
            try:
            	itemIcon = Gtk.IconTheme.get_default().load_icon("folder" if itemIsFolder else "gnome-mime-text-x-c" if os.path.splitext(itemFullname)[1] == '.c' else "gnome-mime-text-x-c++" if os.path.splitext(itemFullname)[1] == '.cpp' else "gnome-mime-text-x-python" if os.path.splitext(itemFullname)[1] == '.py' else "application-json" if os.path.splitext(itemFullname)[1] == '.json' else "text-x-markdown" if os.path.splitext(itemFullname)[1] == '.md' else "text-x-cmake" if os.path.basename(itemFullname) == 'Makefile' else "gnome-mime-image" if os.path.splitext(itemFullname)[1] in ['.png', '.jpg', '.jpeg', '.gif'] else "text-x-script" if not self.is_exe(os.path.join(self.projectPath, itemFullname)) else "application-x-executable", 22, 0)
            except:
            	itemIcon = Gtk.IconTheme.get_default().load_icon("text-x-script", 22, 0)

            # print('{} is equal to Makefile? {}'.format(itemFullname, itemFullname == 'Makefile'))
            # Append the item to the TreeStore
            currentIter = treeStore.append(parent, [item, itemIcon, itemFullname])
            # add dummy if current item was a folder
            if itemIsFolder: treeStore.append(currentIter, [None, None, None])
            #increment the item counter
            itemCounter += 1
        # add the dummy node back if nothing was inserted before
        if itemCounter < 1: treeStore.append(parent, [None, None, None])

    def onRowExpanded(self, treeView, treeIter, treePath):
        # get the associated model
        treeStore = treeView.get_model()
        # get the full path of the position
        newPath = treeStore.get_value(treeIter, 2)
        # populate the subtree on curent position
        self.populateFileSystemTreeStore(treeStore, newPath, treeIter)
        # remove the first child (dummy node)
        treeStore.remove(treeStore.iter_children(treeIter))

    def onRowCollapsed(self, treeView, treeIter, treePath):
        # get the associated model
        treeStore = treeView.get_model()
        # get the iterator of the first child
        currentChildIter = treeStore.iter_children(treeIter)
        # loop as long as some childern exist
        while currentChildIter:
            # remove the first child
            treeStore.remove(currentChildIter)
            # refresh the iterator of the next child
            currentChildIter = treeStore.iter_children(treeIter)
        # append dummy node
        treeStore.append(treeIter, [None, None, None])

    def openFileFromTemp(self, *args):
        text = self.tempFilesText[self.curFileIndex]
        self.sbuff.set_text(text)
        self.sbuff.set_language(self.langs[self.curFileIndex])
        self.hb.set_subtitle(self.projectPath + '/' + self.files[self.curFileIndex])

        if self.sbuff.get_language().get_name().lower() == "markdown":
            self.sviewPaned.get_child2().show()
            self.mdPreviewer.load_uri('file://' + os.path.dirname(os.path.abspath(__file__)) + '/browser/index.html')
            self.mdPreviewer.execute_script('writeMd(\'' + re.escape(text) + '\');')
        else:
            self.sviewPaned.get_child2().hide()

    def openFile(self, filePath, *args):

        found = False
        index = None

        for i,f in enumerate(self.filesObject):
            if f['path'] == filePath:
                found = True
                index = i
                break

        if found:
            self.curFileIndex = index
            f = self.filesObject[self.curFileIndex]
            # print(f)
            # print(len(self.filesObject))
            # print(self.curFileIndex)
            self.sbuff.set_text(f['curText'])
            self.sbuff.set_language(f['language'])
            self.hb.set_subtitle(f['path'])

            if self.sbuff.get_language().get_name().lower() == "markdown":
                self.sviewPaned.get_child2().show()
                self.mdPreviewer.execute_script('writeMd("' + re.escape(self.getCurrentText()) + '");')
                # print(re.escape(self.getCurrentText()))
            else:
                self.sviewPaned.get_child2().hide()

        else:
            with open(filePath, 'r') as f:
                txt = f.read()
                lang = self.lmngr.guess_language(filePath)

                # if not lang:
                #     if os.path.basename(filePath).lower() == 'makefile':
                #         lang =

                self.filesObject.append({
                    'type': 'file',
                    'path': filePath,
                    'curText': txt,
                    'originalText': txt,
                    'language': lang
                })

                self.curFileIndex = len(self.filesObject) - 1
                self.hb.set_subtitle(filePath)

                self.sbuff.set_text(txt)

                # self.langs[self.curFileIndex] = lang
                self.currentLanguage = lang
                self.sbuff.set_language(lang)
                self.hb.set_subtitle(filePath)

                # print(self.getCurrentText())

                if not self.sbuff.get_language() is None and self.sbuff.get_language().get_name().lower() == "markdown":
                    self.sviewPaned.get_child2().show()
                    self.mdPreviewer.execute_script('writeMd("' + re.escape(self.getCurrentText()) + '");')
                    # print(re.escape(self.getCurrentText()))
                else:
                    self.sviewPaned.get_child2().hide()

    def saveFile(self, *args):
        if type(self.curFileIndex) is not int:
            print('no files open')
            return
        _f = self.filesObject[self.curFileIndex]['path']
        with open(_f, 'w') as f:
            text = self.getCurrentText()
            f.write(text)
            self.filesObject[self.curFileIndex]['originalText'] = text
        print("Tried to save {}".format(_f))

        curSettings = None

        if _f == os.path.join(os.path.abspath(__file__), 'pyide-settings.json'):
            with open(os.path.join(os.path.abspath(__file__), 'pyide-settings.json'), 'r') as f:
                curSettings = json.load(f)
                #print(self.curSettings == curSettings)
            if self.curSettings != curSettings:
                self.loadSettings()

    def buildTree(self, *args):

        for item in self.files:
            a = Gtk.Label(item)
            if os.path.isdir(self.projectPath + '/' + item):
                i = Gtk.Image.new_from_icon_name('folder', Gtk.IconSize.MENU) # change this for recursive function
            else:
                i = Gtk.Image.new_from_icon_name('text-x-script', Gtk.IconSize.MENU)
            hb = Gtk.HBox(spacing=6)
            hb.pack_start(i, False, False, 0)
            hb.pack_start(a, False, False, 0)

            row = Gtk.ListBoxRow()
            row.add(hb)
            self.sideView.add(row)

        self.sideView.show_all()

    def entryDialog(self, message, title='', defaultText=''):
        # Returns user input as a string or None
        # If user does not input text it returns None, NOT AN EMPTY STRING.
        dialogWindow = Gtk.MessageDialog(self, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.INFO, Gtk.ButtonsType.OK_CANCEL, message)

        dialogWindow.set_title(title)

        dialogBox = dialogWindow.get_content_area()
        userEntry = Gtk.Entry()
        userEntry.set_text(defaultText)
        dialogBox.pack_end(userEntry, False, False, 0)

        dialogWindow.show_all()
        response = dialogWindow.run()
        text = userEntry.get_text()
        dialogWindow.destroy()
        if (response == Gtk.ResponseType.OK) and (text != ''):
            return text
        else:
            return None

    def confirm(self, message):
        dialogWindow = Gtk.MessageDialog(self, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.INFO, Gtk.ButtonsType.OK_CANCEL, message)
        response = dialogWindow.run()
        dialogWindow.destroy()
        return (response == Gtk.ResponseType.OK)



    def compile(self, *args):

        if self.running:
            ##
            self.comp._quit()
        else:

            self.comp = Compiler(self, self.projectPath, self.stateEntry, self.compileBtn)
            self.comp.compile()

    def createNewFile(self, *args):
        filename = self.entryDialog('File Path', 'Please type in the path starting from ' + self.projectPath, '')

        if not filename is None:
            print(os.path.join(self.projectPath, filename))
            if not os.path.isfile(os.path.join(self.projectPath, filename)):
                open(os.path.join(self.projectPath, filename), 'w+')
                self.openProject(self.projectPath)

    def createNewFolder(self, *args):
        foldername = self.entryDialog('Folder Path', 'Please type in the path starting from ' + self.projectPath, '')

        if not foldername is None:
            print(os.path.join(self.projectPath, foldername))
            os.makedirs(os.path.join(self.projectPath, foldername), exist_ok=True)
            self.openProject(self.projectPath)

if len(sys.argv) == 1:
    w = wW.WelcomeWindow()
elif len(sys.argv) == 2:
    a = IDEWindow(sys.argv[1])
else:
    print('Wrong use, usage: python3 main.py [PATH/TO/FOLDER OR NONE]')
