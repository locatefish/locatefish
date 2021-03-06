#!/usr/bin/env python

# Copyright (C) 2007-2008 Christian Dywan <christian at twotoasts dot de>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# See the file COPYING for the full license text.

import sys

try:
    import os, stat, time, md5, optparse, subprocess, re, datetime, mimetypes

    from os.path import split as split_filename
    from shutil import copy2

    import xdg.Mime

    import locale, gettext
    from gi.repository import GObject, Gtk, Gdk, GdkPixbuf, Pango
    from gi._gi import _glib
    from _glib import GError

except ImportError, msg:
    print 'Error: The required module %s is missing.' % str(msg).split()[-1]
    sys.exit(1)

app_name = 'locatefish'
app_version = '0.1.1'

_ = gettext.gettext # i18n shortcut

from itertools import permutations

def string_regex(string):
    keywords = string.split(' ')
    perms = []
    perm = permutations(keywords)
    p = perm.next()
    regex = ""
    try:
        while p != None:
            perms.append(p)
            p = perm.next()
    except StopIteration:
        pass

    first_string = True
    for permutation in perms:
        strperm = ""
        first = True
        for string in permutation:
            if first:
                first = False
                strperm += string
            else:
                strperm += "(.)*" + string
        if first_string:
            first_string = False
            regex = strperm
        else:
            regex += '|' + strperm
    return regex

def detach_cb(menu, widget):
    menu.detach()

def menu_position(self, menu, data=None, something_else=None):
    widget = menu.get_attach_widget()
    allocation = widget.get_allocation()
    window_pos = widget.get_window().get_position()
    x = (window_pos[0] + allocation.x - menu.get_allocated_width() +
         widget.get_allocated_width())
    y = window_pos[1] + allocation.y + allocation.height
    return (x, y, True)


class IntersectionError(ValueError):
    pass
    

class Filter(object):
    def __init__(self, intersect, matchcase, hidden, start_date, end_date,
                 time_format, type_families, custom_mime, custom_extensions):
        self.intersect = intersect # intersect search terms
        self.matchcase = matchcase # case sensitive
        self.hidden = hidden # show hidden files
        #self.fulltext = bool(fulltext)
        self.start_date = start_date
        self.end_date = end_date
        self.time_format = time_format
        self.type_families = type_families
        self.custom_mime = custom_mime
        self.custom_extensions = []
        for ext in custom_extensions:
            if ext[0] != '.':
                self.custom_extensions.append('.' + ext)
            else:
                self.custom_extensions.append(ext)
        self.mimetype_overrides = {'.abw': 'text', '.ai': 'text',
        '.cdy': 'video', '.chrt': 'text', '.doc':'text', '.docm':'text',
        '.docx':'text', '.dot':'text', '.dotm':'text', '.dotx':'text',
        '.eps':'text', '.gnumeric':'text', '.kil':'text', '.kpr':'text',
        '.kpt':'text', '.ksp':'text', '.kwd':'text', '.kwt':'text',
        '.latex':'text', '.mdb':'text', '.mm':'text', '.nb':'text',
        '.nbp':'text', '.odb':'text', '.odc':'text', '.odf':'text',
        '.odg':'image', '.odi':'image', '.odm':'text', '.odp':'text',
        '.ods':'text', '.odt':'text', '.otg':'text', '.oth':'text',
        '.odp':'text', '.ots':'text', '.ott':'text', '.pdf': 'text',
        '.php':'text', '.pht':'text', '.phtml':'text', '.potm':'text',
        '.potx':'text', '.ppa':'text', '.ppam':'text', '.pps':'text',
        '.ppsm':'text', '.ppsx':'text', '.ppt':'text', '.pptm':'text',
        '.pptx':'text', '.ps':'text', '.pwz':'text', '.rtf':'text',
        '.sda':'text', '.sdc':'text', '.sdd':'text', '.sds':'text',
        '.sdw':'text', '.stc':'text', '.std':'text', '.sti':'text',
        '.stw':'text', '.sxc':'text', '.sxd':'text', '.sxg':'text',
        '.sxi':'text', '.sxm':'text', '.sxw':'text', '.wiz':'text',
        '.wp5':'text', '.wpd':'text', '.xlam':'text', '.xlb':'text',
        '.xls':'text', '.xlsb':'text', '.xlsm':'text', '.xlsx':'text',
        '.xlt':'text', '.xltm':'text', '.xlsx':'text', '.xml':'text'}

    def apply_filters(self, fileobject, modification_date):
        show_file = True
        if isinstance(fileobject, str):
            filename = fileobject
            is_hidden = self.file_is_hidden(filename)
            if isinstance(modification_date, str):
                modification_date = datetime.datetime.strptime(modification_date,
                                                               self.time_format)
            mime_type = self.determine_mimetype(filename)
        else:
            filename = fileobject[0]
            is_hidden = fileobject[1]
            modification_date = fileobject[2]
            mime_type = fileobject[3]
        name = os.path.split(filename)[1]

        if not self.date_in_range(modification_date):
            show_file = False
        if not self.filetype_is_wanted(filename, mime_type[1]):
            show_file = False
        if not self.hidden and is_hidden:
            show_file = False
        return show_file, is_hidden, modification_date, mime_type

    def file_is_hidden(self, filename):
        """Determine if a file is hidden or in a hidden folder"""
        if filename == '': return False
        path, name = os.path.split(filename)
        if len(name) and name[0] == '.':
            return True
        for folder in path.split(os.path.sep):
            if len(folder):
                if folder[0] == '.':
                    return True
        return False

    def date_in_range(self, datetimeobject):
        if self.start_date == self.end_date:
            start_date = self.start_date - datetime.timedelta(days=1)
            end_date = self.end_date + datetime.timedelta(days=1)
            return start_date <= datetimeobject and end_date >= datetimeobject
        return self.start_date <= datetimeobject and self.end_date >= datetimeobject

    def filetype_is_wanted(self, filename, mime_type):
        if (len(self.type_families) == 0 and len(self.custom_extensions) == 0
            and self.custom_mime == [None, None]):
            return True
        if mime_type == self.custom_mime:
            return True
        extension = os.path.splitext(filename)[1]
        if extension in self.mimetype_overrides.keys():
            if self.mimetype_overrides[extension] in self.type_families:
                return True
        if extension in self.custom_extensions:
            return True
        if 'application' in self.type_families:
            if extension in ['.exe', '.app', '.desktop']:
                return True
            if mime_type[1] == 'x-executable':
                return True
        if mime_type[0] in self.type_families and mime_type[0] != 'application':
            return True
        return False

    def determine_mimetype(self, filename):
        file_type = []
        ext = os.path.splitext(filename)[1]
        mime = xdg.Mime.get_type(filename)
        if ext in self.mimetype_overrides.keys():
            file_type.append( self.mimetype_overrides[ext] )
        else:
            file_type.append(mime.media)
        file_type.append([mime.media, mime.subtype])
        return file_type


class shell_query(object):
    def __init__(self, method, method_args):
        self.err = ''
        self.method = method
        self.method_args = method_args

    def run(self, keywords, folder, intersect, matchcase, hidden, limit):
        """Run the query subprocess. keywords is a list of (multi)words"""
        case, nocase = self.method_args
        # build up shell command:
        command = self.method
        if matchcase:
            command += ' ' + case
        else:
            command += ' ' + nocase
        # disable limit for now:
        #if limit > 0:
        #    command += ' ' + limit_results
        # surround each keyword with *, prepend folder:
        keywords = [ os.path.join(folder, '*%s*' % keyword) for keyword in keywords ]
        # rebuild space separated string, with quotes around each (multi)word:
        keywords = ' '.join([ '"%s"' % keyword for keyword in keywords ])
        command += ' ' + keywords
        # print out query command:
        print command
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, shell=True)
        return self.process.stdout
        
    def status(self):
        """From locate manual: if no match was found or a fatal error was encountered,
        locate exits with status 1"""
        return self.err or self.process.poll()


class Locatefish(object):
    def __init__(self):
        """Create the main window."""
        self.open_wrapper = 'xdg-open'

        # Parse command line options
        parser = optparse.OptionParser(usage='usage: ' + app_name + ' [options] keywords',
                                       version=app_name + ' v' + app_version)
        parser.add_option('', '--large-icons', action='store_true', dest='icons_large',
                          help='Use large icons')
        parser.add_option('', '--thumbnails', action='store_true', dest='thumbnails',
                          help='Use thumbnails')
        parser.add_option('', '--iso-time', action='store_true', dest='time_iso',
                          help='Display time in iso format')
        parser.add_option('', '--limit', type='int', metavar='LIMIT', dest='limit_results',
                          help='Limit number of results')
        parser.add_option('', '--path', help='Search in folder PATH')
        parser.add_option('', '--fileman', help='Use FILEMAN as filemanager')
        parser.add_option('', '--wrapper', metavar='WRAPPER', dest='open_wrapper',
                          help='Use WRAPPER to open files')
        parser.add_option('', '--method', help='Use METHOD to search')
        parser.add_option('', '--intersect', action='store_true',
                          help='Intersect results from search terms')
        parser.add_option('', '--matchcase', action='store_true', help='Match case')
        parser.add_option('', '--hidden', action='store_true', help='Include hidden files')
        #parser.add_option('', '--fulltext', action='store_true',
        #                   help='Perform fulltext search')
        parser.add_option('', '--file-action', metavar='ACTION', dest='file_action',
                          help='File action: "open" or "folder"')
        parser.add_option('', '--debug', action='store_true', help='Show debugging messages.')
        parser.set_defaults(icons_large=False, thumbnails=False, time_iso=True,
                            method='locate', limit_results=False, path='~/papers',
                            fileman=self.open_wrapper, intersect=True, matchcase=False,
                            hidden=True, file_action='open', debug=False,
                            open_wrapper=self.open_wrapper)
        self.options, args = parser.parse_args()
        keywords = ' '.join(args)

        if not self.options.file_action in ('open', 'folder'):
            print 'Error: Invalid value for "file-action".\n'
            print 'Use either "open" to open files by default or'
            print 'use "folder" to open the containing folder.'
            print '(The default is "open".)'
            sys.exit(1)

        if not self.options.fileman:
            print 'Warning: No file manager was found or specified.'

        # Prepare i18n using gettext
        try:
            locale.setlocale(locale.LC_ALL, '')
            locale.bindtextdomain(app_name, 'locale')
            gettext.bindtextdomain(app_name, 'locale')
            gettext.textdomain(app_name)
        except Exception, msg:
            if self.options.debug: print 'Debug:', msg
            print 'Warning: Invalid locale, i18n is disabled.'

        # Guess location of glade file
        glade_file = app_name + '.glade'
        glade_path = os.getcwd()
        if not os.path.exists(os.path.join(glade_path, glade_file)):
            glade_path = os.path.dirname(sys.argv[0])
            if not os.path.exists(os.path.join(glade_path, glade_file)):
                print 'Error: The glade file could not be found.'
                sys.exit()

        # Load interface from glade file and retrieve widgets
        self.load_interface(os.path.join(glade_path, glade_file))

        # Set some initial values
        self.icon_cache = {}
        self.icon_theme = Gtk.IconTheme.get_default()
        self.checkbox_find_intersect.set_active(self.options.intersect)
        self.checkbox_find_matchcase.set_active(self.options.matchcase)
        self.checkbox_find_hidden.set_active(self.options.hidden)
        #self.checkbox_find_fulltext.set_active(self.options.fulltext)
        if self.options.limit_results:
            self.checkbox_find_limit.set_active(1)
            self.checkbox_find_limit.toggled()
            self.spin_find_limit.set_value(self.options.limit_results)
        self.folder_thumbnails = os.path.expanduser('~/.thumbnails/normal/')
        self.options.path = os.path.abspath(os.path.expanduser(self.options.path))
        if not os.path.isdir(self.options.path):
            self.options.path = os.path.expanduser('~')
        self.button_find_folder.set_current_folder(self.options.path)
        self.link_color = None
        # TODO: FIX ME, LINK COLOR
        #try:
        #    self.link_color = GObject.Value()
        #    self.link_color.init(Gdk.Color)
        #    self.treeview_files.style_get_property('link-color', self.link_color)
        #    print self.link_color.get_gtype()
        #except Exception as err:
        #    print err
        #    self.link_color = None
        if self.link_color == None:
            self.link_color = 'blue'

        # Set up keywords completion
        completion = Gtk.EntryCompletion()
        self.entry_find_text.set_completion(completion)
        listmodel = Gtk.ListStore(str)
        completion.set_model(listmodel)
        completion.set_text_column(0)

        # Retrieve available search methods
        methods = ['locate']#['find', 'locate', 'slocate', 'tracker', 'doodle']

        bin_dirs = os.environ.get('PATH', '/usr/bin').split(os.pathsep)
        listmodel = Gtk.ListStore(GdkPixbuf.Pixbuf, str)
        method_default = -1
        icon = self.get_icon_pixbuf(Gtk.STOCK_EXECUTE)
        for method in methods:
            for path in bin_dirs:
                if os.path.exists(os.path.join(path, method)):
                    listmodel.append([icon, method])
                    if self.options.method == method:
                        method_default = len(listmodel) - 1
                    break
        if method_default < 0:
            print 'Warning: Method "%s" is not available' % self.options.method
            method_default = 0

        if self.options.icons_large or self.options.thumbnails:
            pr = Gtk.TreeViewColumn(_('Preview'), Gtk.CellRendererPixbuf(), pixbuf=0)
            fn = self.new_column(_('Filename'), 1, markup=0)
            columns = [pr, fn]
        else:
            fn = self.new_column(_('Filename'), 1, special='icon', markup=0, ellipsize=None)
            #fn.set_expand(True)
            lc = self.new_column(_('Location'), 2, ellipsize=None)
            sz = self.new_column(_('Size'), 3, special='filesize')
            md = self.new_column(_('Last modified'), 4, markup=0)
            columns = [fn, lc, sz, md]
        for column in columns:
            column.set_reorderable(True)
            self.treeview_files.append_column(column)

        self.entry_find_text.set_text(keywords)

        self.find_in_progress = False
        self.results = []

        self.updatedb_done = False

        # This variable shows that find was used for a set of results.
        self.find_powered = False

        self.window_search.show_all()

# -- helper functions --

    def load_interface(self, filename):
        """Load glade file and retrieve widgets."""

        # Load interface from the glade file
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(app_name)
        self.builder.add_from_file(filename)

        # Retrieve significant widgets
        self.window_search = self.builder.get_object('window_search')
        self.window_search.set_wmclass ("locatefish", "locatefish")

        self.toolbar = self.builder.get_object('toolbar')
        context = self.toolbar.get_style_context()
        context.add_class(Gtk.STYLE_CLASS_PRIMARY_TOOLBAR)

        self.button_find_folder = self.builder.get_object('button_find_folder')
        self.entry_find_text = self.builder.get_object('entry_find_text')
        self.box_main_controls = self.builder.get_object('box_main_controls')

        self.box_infobar = self.builder.get_object('box_infobar')

        # Application Menu
        self.menu_button = self.builder.get_object('menu_button')
        self.application_menu = self.builder.get_object('application_menu')
        self.checkbox_find_intersect = self.builder.get_object('checkbox_find_intersect')
        self.checkbox_find_matchcase = self.builder.get_object('checkbox_find_matchcase')
        self.checkbox_find_hidden = self.builder.get_object('checkbox_find_hidden')
        #self.checkbox_find_fulltext = self.builder.get_object('checkbox_find_fulltext')
        self.checkbox_advanced = self.builder.get_object('checkbox_advanced')
        self.application_menu.attach_to_widget(self.menu_button, detach_cb)

        # Treeview and Right-Click menu
        self.scrolled_files = self.builder.get_object('scrolled_files')
        self.treeview_files = self.builder.get_object('treeview_files')
        self.menu_file = self.builder.get_object('menu_file')
        self.menu_file_open = self.builder.get_object('menu_open')
        self.menu_file_goto = self.builder.get_object('menu_goto')
        self.menu_file_copy = self.builder.get_object('menu_copy')
        self.menu_file_save = self.builder.get_object('menu_save')

        self.spinner = self.builder.get_object('spinner')
        self.statusbar = self.builder.get_object('statusbar')

        # Sidebar
        self.sidebar = self.builder.get_object('sidebar')
        self.box_type_filter = self.builder.get_object('box_type_filter')
        self.time_filter_any = self.builder.get_object('time_filter_any')
        self.time_filter_week = self.builder.get_object('time_filter_week')
        self.time_filter_custom = self.builder.get_object('time_filter_custom')
        self.button_time_filter_custom = self.builder.get_object('button_time_filter_custom')
        self.type_filter_documents = self.builder.get_object('type_filter_documents')
        self.type_filter_pictures = self.builder.get_object('type_filter_pictures')
        self.type_filter_music = self.builder.get_object('type_filter_music')
        self.type_filter_videos = self.builder.get_object('type_filter_videos')
        self.type_filter_applications = self.builder.get_object('type_filter_applications')
        self.type_filter_other = self.builder.get_object('type_filter_other')
        self.button_type_filter_other = self.builder.get_object('button_type_filter_other')


        self.aboutdialog = self.builder.get_object('aboutdialog')

        self.date_dialog = self.builder.get_object('date_dialog')
        label_startdate = self.builder.get_object('label_startdate')
        label_enddate = self.builder.get_object("label_enddate")
        self.box_calendar_end = self.builder.get_object('box_calendar_end')
        self.box_calendar_start = self.builder.get_object('box_calendar_start')
        self.calendar_start = Gtk.Calendar()
        calendar_start_today = self.builder.get_object('calendar_start_today')
        calendar_end_today = self.builder.get_object('calendar_end_today')
        self.calendar_end = Gtk.Calendar()
        self.box_calendar_start.pack_start(self.calendar_start, True, True, 0)
        self.box_calendar_end.pack_start(self.calendar_end, True, True, 0)

        self.mimetypes_dialog = self.builder.get_object('mimetypes_dialog')
        self.combobox_mimetype_existing = self.builder.get_object('combobox_mimetype_existing')
        self.entry_mimetype_custom = self.builder.get_object('entry_mimetype_custom')
        self.radio_mimetype_existing = self.builder.get_object('radio_mimetype_existing')
        radio_mimetype_custom = self.builder.get_object('radio_mimetype_custom')
        self.load_mimetypes()

        self.dialog_updatedb = self.builder.get_object('dialog_updatedb')
        dialog_updatedb_text_primary = self.builder.get_object('dialog_updatedb_text_primary')
        dialog_updatedb_text_secondary = self.builder.get_object('dialog_updatedb_text_secondary')
        self.updatedb_spinner = self.builder.get_object('updatedb_spinner')
        self.updatedb_label_updating = self.builder.get_object('updatedb_label_updating')
        self.updatedb_label_done = self.builder.get_object('updatedb_label_done')
        self.updatedb_button_cancel = self.builder.get_object('updatedb_button_cancel')
        self.updatedb_button_ok = self.builder.get_object('updatedb_button_ok')

        # Localized strings
        self.entry_find_text.set_placeholder_text( _("Search terms") )

        self.checkbox_find_intersect.set_label( _("Intersect terms") )
        self.checkbox_find_matchcase.set_label( _("Match case") )
        self.checkbox_find_hidden.set_label( _("Hidden files") )
        #self.checkbox_find_fulltext.set_label( _("Fulltext search") )
        self.checkbox_advanced.set_label( _("Advanced Filtering") )

        self.time_filter_any.set_label( _("Any time") )
        self.time_filter_week.set_label( _("Past week") )
        self.time_filter_custom.set_label( _("Other") )
        self.button_time_filter_custom.set_label( _("Custom...") )

        self.type_filter_documents.set_label( _("Documents") )
        self.type_filter_pictures.set_label( _("Images") )
        self.type_filter_music.set_label( _("Music") )
        self.type_filter_videos.set_label( _("Videos") )
        self.type_filter_applications.set_label( _("Applications") )
        self.type_filter_other.set_label( _("Other") )
        self.button_type_filter_other.set_label( _("Custom...") )

        self.date_dialog.set_title( _("Custom Time Range") )
        label_startdate.set_label( _("Start Date") )
        label_enddate.set_label( _("End Date") )
        calendar_start_today.set_label( _("Today") )
        calendar_end_today.set_label( _("Today") )

        self.mimetypes_dialog.set_title( _("Custom File Filter") )
        self.radio_mimetype_existing.set_label( _("Existing mimetype") )
        radio_mimetype_custom.set_label( _("Enter extensions") )

        self.dialog_updatedb.set_title( _("Update Search Index") )
        dialog_updatedb_text_primary.set_markup('<big><b>%s</b></big>' %
                                                _("Update Search Index"))
        dialog_updatedb_text_secondary.set_label( _("To provide accurate results, the "
        "locate database needs to be refreshed.\nThis requires sudo (admin) rights.") )
        self.updatedb_label_updating.set_label( _("Updating database...") )
        self.updatedb_label_done.set_label( _("Done.") )

        # Signals
        self.calendar_start.connect("day-selected", self.on_filter_changed)
        self.calendar_start.connect("month-changed", self.on_filter_changed)
        self.calendar_end.connect("day-selected", self.on_filter_changed)
        self.calendar_end.connect("month-changed", self.on_filter_changed)

        self.window_search.connect("key-press-event", self.on_keypress)
        self.builder.connect_signals(self)

    def compare_dates(self, model, row1, row2, user_data):
        """Compare 2 dates, used for sorting modification dates."""
        sort_column, _ = model.get_sort_column_id()
        if not self.options.time_iso:
            time_format = '%x %X'
        else:
            time_format = '%Y-%m-%d %H:%M'
        value1 = time.strptime(model.get_value(row1, sort_column), time_format)
        value2 = time.strptime(model.get_value(row2, sort_column), time_format)
        if value1 < value2:
            return -1
        elif value1 == value2:
            return 0
        else:
            return 1

    def new_column(self, label, id, special=None, markup=0, ellipsize=None):
        if special == 'icon':
            column = Gtk.TreeViewColumn(label)
            cell = Gtk.CellRendererPixbuf()
            column.pack_start(cell, True)
            column.add_attribute(cell, 'pixbuf', 0)
            cell = Gtk.CellRendererText()
            column.pack_start(cell, True)
            if markup:
                column.add_attribute(cell, 'markup', id)
            else:
                column.add_attribute(cell, 'text', id)
        else:
            cell = Gtk.CellRendererText()
            if markup:
                column = Gtk.TreeViewColumn(label, cell, markup=id)
            else:
                column = Gtk.TreeViewColumn(label, cell, text=id)
            if special == 'filesize':
                column.set_cell_data_func(cell, self.cell_data_func_filesize, id)
        if ellipsize:
            width, mode = ellipsize
            column.set_min_width(width)
            cell.set_property('ellipsize', mode)
        column.set_sort_column_id(id)
        column.set_resizable(True)
        return column

    def cell_data_func_filesize(self, column, cell_renderer, tree_model, tree_iter, id):
        filesize = self.format_size(int(tree_model.get_value(tree_iter, id)))
        cell_renderer.set_property('text', filesize)
        return

    def format_size(self, size):
        """Make a file size human readable."""

        if size > 2 ** 30:
            return '%s GB' % (size / 2 ** 30)
        elif size > 2 ** 20:
            return '%s MB' % (size / 2 ** 20)
        elif size > 2 ** 10:
            return '%s kB' % (size / 2 ** 10)
        elif size > -1:
            return '%s B' % size
        else:
            return ''

    def get_error_dialog(self, msg, parent=None):
        """Display modal error dialog."""

        SaveFile = Gtk.MessageDialog(parent, 0,
            Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, msg)
        response = SaveFile.run()
        SaveFile.destroy()
        return response == Gtk.ResponseType.YES

    def get_yesno_dialog(self, msg, parent=None):
        """Display yes/ no dialog and return a boolean value."""

        SaveFile = Gtk.MessageDialog(parent, 0,
            Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, msg)
        SaveFile.set_default_response(Gtk.ResponseType.NO)
        response = SaveFile.run()
        SaveFile.destroy()
        return response == Gtk.ResponseType.YES

    def get_save_dialog(self, parent=None, default_filename=None):
        """Display save dialog and return filename or None."""

        buttons = (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.REJECT)
        SaveFile = Gtk.FileChooserDialog(_('Save "%s" as...') % default_filename, parent,
            Gtk.FileChooserAction.SAVE, buttons)
        SaveFile.set_default_response(Gtk.ResponseType.REJECT)
        SaveFile.set_current_name(default_filename)
        SaveFile.set_do_overwrite_confirmation(True)
        response = SaveFile.run()
        filename = SaveFile.get_filename()
        SaveFile.destroy()
        return [None, filename][response == Gtk.ResponseType.REJECT]

    def treeview_get_selection(self, treeview, event=None):
        """Retrieve the model and path of the selection."""

        model = treeview.get_model()
        if event == None:
            try:
                path = treeview.get_cursor()[0]
                return model, path
            except Exception:
                path = None
        if event <> None:
            # Select the entry at the mouse position
            pathinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
            try:
                path, col, cellx, celly = pathinfo
                treeview.set_cursor(path)
            except Exception:
                path = None
        return model, path

    def get_selected_filename(self, treeview, treeiter=None):
        """Return folder and filename"""
        model, path = self.treeview_get_selection(treeview)
        if path == None:
            return None, None
        if treeiter == None:
            treeiter = model.get_iter(path)
        if model.get_value(treeiter, 3) == None:
            return None, None
        if self.options.icons_large or self.options.thumbnails:
            # these indices might be off:
            filename, folder = model.get_value(treeiter, 4), model.get_value(treeiter, 3)
        else:
            filename, folder = model.get_value(treeiter, 2), model.get_value(treeiter, 1)
        # if markup=1, replace '&amp;' markup with original '&':
        #filename, folder = filename.replace('&amp;', '&'), folder.replace('&amp;', '&')
        return filename, folder

    def open_file(self, filename):
        """Open the file with its default app or the file manager"""
        if os.path.exists(filename):
            command = [self.open_wrapper, filename]
            try:
                subprocess.Popen(command, shell=False)
            except Exception, msg:
                if self.options.debug: print 'Debug:', msg
                self.get_error_dialog(('Error: Could not open the file %s.'
                 % filename), self.window_search)
                print '* The wrapper was %s.' % self.open_wrapper
                print '* The filemanager was %s.' % self.options.fileman
                print 'Hint: Check wether the wrapper and filemanager exist.'
        else:
            self.get_error_dialog(('Error: Could not access the file %s.'
             % filename), self.window_search)

    def get_method_args(self, method, limit=-1):
        if method == 'locate':
            case = ''
            nocase = '-i'
        else:
            raise ValueError('unknown method %r' % method)
        return case, nocase

    def load_mimetypes(self):
        mimetypes.init()
        mimes = mimetypes.types_map.values()
        mimes.sort()
        liststore = Gtk.ListStore(str)
        cell = Gtk.CellRendererText()
        self.combobox_mimetype_existing.pack_start(cell, True)
        self.combobox_mimetype_existing.add_attribute(cell, 'text', 0)
        mime_list = []
        for mime in mimes:
            if mime not in mime_list:
                mime_list.append(mime)
                liststore.append([mime])

        self.combobox_mimetype_existing.set_model(liststore)

    def get_search_settings(self):
        keywords = self.entry_find_text.get_text()
        folder = self.button_find_folder.get_filename()
        intersect = self.checkbox_find_intersect.get_active()
        matchcase = self.checkbox_find_matchcase.get_active()
        hidden = self.checkbox_find_hidden.get_active()
        #fulltext = self.checkbox_find_fulltext.get_active()
        limit = -1

        if self.time_filter_any.get_active():
            start_date = datetime.datetime.min
            end_date = datetime.datetime.max
        elif self.time_filter_week.get_active():
            now = datetime.datetime.now()
            week_ago = now - datetime.timedelta(days=7)
            start_date = datetime.datetime(week_ago.year, week_ago.month, week_ago.day,
                                           0, 0, 0, 0)
            end_date = now + datetime.timedelta(days=1)
            end_date = datetime.datetime(end_date.year, end_date.month, end_date.day,
                                         0, 0, 0, 0)
        else:
            start_date = self.calendar_start.get_date()
            start_date = datetime.datetime(start_date[0], start_date[1]+1, start_date[2])
            end_date = self.calendar_end.get_date()
            end_date = datetime.datetime(end_date[0], end_date[1]+1,
                                         end_date[2]) + datetime.timedelta(days=1)

        type_families = []
        if self.type_filter_documents.get_active():
            type_families.append('text')
        if self.type_filter_pictures.get_active():
            type_families.append('image')
        if self.type_filter_music.get_active():
            type_families.append('audio')
        if self.type_filter_videos.get_active():
            type_families.append('video')
        if self.type_filter_applications.get_active():
            type_families.append('application')

        custom_mime = [None, None]
        custom_extensions = []
        if self.type_filter_other.get_active():
            if self.radio_mimetype_existing.get_active():
                model = self.combobox_mimetype_existing.get_model()
                tree_iter = self.combobox_mimetype_existing.get_active_iter()
                if model and tree_iter:
                    selected_mime = model[tree_iter][0]
                    custom_mime = selected_mime.split('/')
            else:
                ext = self.entry_mimetype_custom.get_text()
                ext = ext.replace(',', ' ')
                custom_extensions = ext.split()

        return (keywords, folder, intersect, matchcase, hidden, limit, start_date, end_date,
                type_families, custom_mime, custom_extensions)

    def find(self, widget=None, method='locate'):
        """Do the actual search."""
        self.box_infobar.hide()
        self.spinner.show()
        self.find_in_progress = True
        self.reset_text_entry_icon()
        self.results = []
        self.window_search.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.WATCH))
        self.window_search.set_title(_('Searching for "%s"') % self.entry_find_text.get_text())
        self.statusbar.push(self.statusbar.get_context_id('results'), _('Searching...'))
        while Gtk.events_pending(): Gtk.main_iteration()

        # Reset treeview
        listmodel = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, long, str)
        self.treeview_files.set_model(listmodel)
        self.treeview_files.columns_autosize()
        listmodel.set_sort_column_id(1, Gtk.SortType.ASCENDING)

        # Retrieve search parameters
        (keywords, folder, intersect, matchcase, hidden, limit, start_date, end_date,
         type_families, custom_mime, custom_extensions) = self.get_search_settings()

        self.window_search.set_title('%s' % keywords)

        if method == 'locate':
            #keywords = keywords.replace('*', ' ') # ignore wildcards
            # find any words in quotes, from http://stackoverflow.com/a/9519934/2020363:
            multiwords = re.findall(r'\"(.+?)\"', keywords)
            for multiword in multiwords:
                keywords = keywords.replace(multiword, '') # remove any multiwords
            # remove any quotes, split by whitespace:
            keywords = keywords.replace('"', '').split()
            keywords.extend(multiwords) # combine into one list

        if not self.options.time_iso:
            time_format = '%x %X'
        else:
            time_format = '%Y-%m-%d %H:%M'

        result_filter = Filter(intersect, matchcase, hidden, start_date, end_date, time_format,
                               type_families, custom_mime, custom_extensions)

        if keywords != '':
            # Generate search command
            self.keywords = keywords
            self.folder = folder
            method_args = self.get_method_args(method)

            # Set display options
            if not self.options.icons_large and not self.options.thumbnails:
                icon_size = Gtk.IconSize.MENU
            else:
                icon_size = Gtk.IconSize.DIALOG

            # Run search command and capture the results
            messages = []
            #if fulltext:
            #    query = fulltext_query(options)
            #else:
            query = shell_query(method, method_args)
            filenames = list(query.run(keywords, folder, intersect, matchcase, hidden, limit))
            for filename in filenames:
                if self.abort_find or len(listmodel) == limit:
                    break
                filename = filename.split(os.linesep)[0]
                # Convert uris to filenames
                if filename[:7] == 'file://':
                    filename = filename[7:]
                # Handle mailbox uris like filenames as well
                if filename[:10] == 'mailbox://':
                    filename = filename[10:]
                    filename = filename[:filename.index('?')]
                path, name = os.path.split(filename)
                if intersect: # ensure each name contains all keywords
                    try:
                        for keyword in keywords:
                            testname = name
                            if not matchcase:
                                keyword = keyword.lower()
                                testname = name.lower()
                            if keyword not in testname:
                                raise IntersectionError
                    except IntersectionError:
                        continue # skip this filename
                #try:
                size = os.path.getsize(filename)
                modified = time.strftime(time_format,
                                         time.localtime(os.path.getmtime(filename)))
                (show_file, is_hidden, modification_date,
                 mime_type) = result_filter.apply_filters(filename, modified)

                if self.options.thumbnails:
                    icon = self.get_thumbnail(filename, icon_size, mime_type)
                else:
                    icon = self.get_file_icon(filename, icon_size, mime_type)

                # required to prevent display issues when markup == 1:
                #name = name.replace('&', '&amp;')
                result = [filename, is_hidden, modification_date, mime_type]
                if not self.options.icons_large and not self.options.thumbnails:
                    result.append([icon, name, path, size, modified])
                    if result not in self.results:
                        if show_file:
                            listmodel.append(result[4])
                        self.results.append(result)
                else:
                    path = path.replace('&', '&amp;')
                    if modified <> '':
                        modified = os.linesep + modified
                    resultstr = '%s %s%s%s%s' % (name, path, os.linesep,
                                                 self.format_size(size) , modified)
                    result.append([icon, resultstr, None, name, path])
                    if result not in self.results:
                        if show_file:
                            listmodel.append(result[4])
                        self.results.append(result)
                #except Exception, msg:
                #    if self.options.debug: print 'Debug:', msg
                #    pass # Ignore inaccessible files
                yield True
            self.treeview_files.set_model(listmodel)
            if len(listmodel) == 0:
                #if query.status():
                #    status_icon = Gtk.STOCK_CANCEL
                #    messages.append([_('Fatal error, search was aborted.'), None])
                #else:
                status_icon = Gtk.STOCK_INFO
                messages.append([_('No files were found.'), None])
                status = _('No files found.')
            else:
                status = _('%s files found.') % str(len(listmodel))
            for message, action in messages:
                icon = [None, self.get_icon_pixbuf(status_icon)][message == messages[0][0]]
                listmodel.append([icon, message, None, None, action])
            self.statusbar.push(self.statusbar.get_context_id('results'), status)
        self.treeview_files.set_model(listmodel)
        listmodel.set_sort_func(4, self.compare_dates, None)

        self.window_search.get_window().set_cursor(None)
        self.keywords = keywords
        self.spinner.hide()
        self.find_in_progress = False
        self.reset_text_entry_icon()
        if method != 'find':
            self.box_infobar.show()
        yield False

    def get_icon_pixbuf(self, name, icon_size=Gtk.IconSize.MENU):
        try:
            return self.icon_cache[name]
        except KeyError:
            icon_size = Gtk.icon_size_lookup(icon_size)[1]
            try:
                icon = self.icon_theme.load_icon(name, icon_size, 0)
                self.icon_cache[name] = icon
                return icon
            except GError:
                return

    def get_thumbnail(self, path, icon_size=0, mime_type=None):
        """Try to fetch a small thumbnail."""
        md5_hash = md5.new('file://' + path).hexdigest()
        filename = '%s%s.png' % (self.folder_thumbnails, md5_hash)
        try:
            return GdkPixbuf.Pixbuf.new_from_file(filename)
        except Exception:
            return self.get_file_icon(path, icon_size, mime_type)

    def get_file_icon(self, path, icon_size=0, mime_type=None):
        """Retrieve the file icon."""
        mime_type = mime_type[1]
        try:
            is_folder = stat.S_ISDIR(os.stat(path).st_mode)
        except Exception:
            is_folder = 0
        if is_folder:
            icon_name = Gtk.STOCK_DIRECTORY
        else:
            if mime_type <> None:
                try:
                    # Get icon from mimetype
                    media, subtype = mime_type
                    icon_name = 'gnome-mime-%s-%s' % (media, subtype)
                    return self.get_icon_pixbuf(icon_name, icon_size)
                except Exception:
                    try:
                        # Then try generic icon
                        icon_name = 'gnome-mime-%s' % media
                        return self.get_icon_pixbuf(icon_name, icon_size)
                    except Exception:
                        # Use default icon
                        icon_name = Gtk.STOCK_FILE
            else:
                icon_name = Gtk.STOCK_FILE
        return self.get_icon_pixbuf(icon_name, icon_size)

    def reset_text_entry_icon(self):
        eft = self.entry_find_text
        if self.find_in_progress:
            eft.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_CANCEL)
            eft.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _('Cancel search') )
        elif len(eft.get_text()) > 0:
            eft.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_CLEAR)
            eft.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _('Clear search terms'))
        else:
            eft.set_icon_from_stock(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_FIND)
            eft.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY,
                                      _('Enter search terms and press ENTER'))

    def disable_filters(self):
        self.time_filter_any.set_active(True)
        for checkbox in self.box_type_filter.get_children():
            try:
                checkbox.set_active(False)
            except AttributeError:
                pass

# -- events --

    def on_window_search_destroy(self, widget):
        """When the application window is closed, end the program."""
        Gtk.main_quit()

    def on_keypress(self, widget, event):
        """When a keypress is detected, do the following:

        ESCAPE      Stop search/Clear Search terms
        Ctrl-Q      Exit
        Ctrl-W      Exit"""
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        keyname = Gdk.keyval_name(event.keyval)
        if ctrl:
            if keyname == 'q' or keyname == 'w':
                Gtk.main_quit()
        else:
            if keyname == 'Escape':
                if self.find_in_progress:
                    self.abort_find = 1
                else:
                    self.entry_find_text.set_text('')

    # Keyword/Search Terms entry
    def on_entry_find_text_changed(self, widget):
        """When text is modified in the search terms box, change the
        icon as necessary"""
        self.reset_text_entry_icon()

    def on_entry_find_text_activate(self, widget):
        """Initiate the search thread."""
        if len(self.entry_find_text.get_text()) == 0:
            return
        if not self.scrolled_files.get_visible():
            self.scrolled_files.set_visible(True)
            self.window_search.set_size_request(640, 400)

        if not self.find_in_progress:
            self.abort_find = 0
            task = self.find()
            GObject.idle_add(task.next)
        else:
            self.abort_find = 1

    def on_entry_find_text_icon_clicked(self, widget, event, data):
        """When the search/clear/stop icon is pressed, perform the
        appropriate action."""
        if self.find_in_progress:
            self.abort_find = 1
        else:
            self.entry_find_text.set_text('')

    # Application Menu
    def on_menu_button_clicked(self, widget):
        """When the menu button is clicked, display the appmenu."""
        self.application_menu.popup(None, None, menu_position,
                                    self.application_menu, 3,
                                    Gtk.get_current_event_time())

    def on_application_menu_hide(self, widget):
        """When the application menu is unfocused (menu item activated
        or clicked elsewhere), unclick the button."""
        self.menu_button.set_active(False)

    def on_checkbox_find_intersect_toggled(self, widget):
        self.on_filter_changed(widget)

    def on_checkbox_find_matchcase_toggled(self, widget):
        self.on_filter_changed(widget)
        #if not self.find_powered:
        #    self.on_button_search_find_clicked(widget)

    def on_checkbox_advanced_toggled(self, widget):
        """When the Advanced Filters toggle is activated, show/hide the
        advanced filters panel."""
        self.sidebar.set_visible(widget.get_active())
        if not widget.get_active():
            self.disable_filters()

    # Update Locate Database Dialog
    def on_menu_updatedb_activate(self, widget):
        """Show the Update Locate Database dialog."""
        self.dialog_updatedb.show()
        self.dialog_updatedb.run()

    def on_updatedb_button_cancel_clicked(self, widget):
        self.dialog_updatedb.hide()
        self.updatedb_label_updating.set_visible(False)
        self.updatedb_label_done.set_visible(False)

    def on_dialog_updatedb_delete_event(self, widget, event):
        """Prevent updatedb dialog from being closed if in progress."""
        try:
            if self.updatedb_in_progress:
                return True
            else:
                self.updatedb_label_updating.set_visible(False)
                self.updatedb_label_done.set_visible(False)
                return False
        except AttributeError:
            self.updatedb_label_updating.set_visible(False)
            self.updatedb_label_done.set_visible(False)
            return False

    def on_dialog_updatedb_run(self, widget):
        """Request admin rights with gksudo and run updatedb."""
        if self.updatedb_done:
            self.dialog_updatedb.hide()
            self.updatedb_done = False
            self.updatedb_label_updating.set_visible(False)
            self.updatedb_label_done.set_visible(False)
        else:
            def updatedb_subprocess():
                done = self.updatedb_process.poll() != None
                if done:
                    self.updatedb_label_updating.set_sensitive(False)
                    self.updatedb_spinner.set_visible(False)
                    self.updatedb_button_cancel.set_sensitive(True)
                    self.updatedb_button_ok.set_sensitive(True)
                    return_code = self.updatedb_process.returncode
                    if return_code == 0:
                        status = _('Locate database updated successfully.')
                    else:
                        status = _('An error occurred while updating locatedb.')
                    self.updatedb_done = True
                    self.updatedb_in_progress = False
                    self.updatedb_label_done.set_label(status)
                    self.updatedb_label_done.set_visible(True)
                return not done
            self.updatedb_spinner.set_visible(True)
            self.updatedb_label_updating.set_visible(True)
            self.updatedb_in_progress = True
            self.updatedb_button_cancel.set_sensitive(False)
            self.updatedb_button_ok.set_sensitive(False)
            self.updatedb_process = subprocess.Popen(['gksudo', 'updatedb'],
                                                     stdout=subprocess.PIPE,
                                                     stderr=subprocess.PIPE, shell=False)
            GObject.timeout_add(1000, updatedb_subprocess)

    def on_menu_about_activate(self, widget):
        """Show the About dialog."""
        self.aboutdialog.show()
        self.aboutdialog.run()
        self.aboutdialog.hide()

    # Search Results TreeView
    def on_treeview_files_row_activated(self, widget, path, column):
        """When a row is activated (SPACE, ENTER, double-clicked), open
        the file/folder if possible."""
        try:
            if self.options.file_action == 'open':
                self.on_menu_open_activate(None)
            else:
                self.on_menu_goto_activate(None)
        except AttributeError:
            pass

    def on_treeview_files_button_pressed(self, treeview, event):
        """Show a popup menu for files or handle clicked links."""
        pri, sec = self.get_selected_filename(treeview)
        if event.button == 1:
            if pri == None:
                return
            model, path = self.treeview_get_selection(treeview, event)
            if path == None:
                return
            action = model.get_value(model.get_iter(path), 4)
            if sec == None and action <> None:
                try:
                    action = re.sub('<[^>]+>', '', action)
                    action_name, action_value = action.split(':')
                    subprocess.Popen([action_value])
                    icon, message = Gtk.STOCK_INFO, _('The search daemon was started.')
                except Exception, msg:
                    if self.options.debug: print 'Debug:', msg
                    icon, message = (Gtk.STOCK_CANCEL
                     , _('The search daemon could not be started.'))
                    print 'Error: %s could not be run.' % action_value
                listmodel = Gtk.ListStore(GdkPixbuf.Pixbuf, str, long, str, str, long)
                listmodel.append([self.get_icon_pixbuf(icon), message, -1, None, None, -1])
                self.treeview_files.set_model(listmodel)
        elif event.button == 2:
            if pri <> None:
                self.open_file(pri)
        elif event.button == 3:
            if sec <> None:
                self.menu_file.popup(None, None, None, None, event.button, event.time)

    def on_treeview_files_popup(self, treeview):
        """Display right-click popup menu for the selected file."""
        pri, sec = self.get_selected_filename(treeview)
        if sec <> None:
            self.menu_file.popup(None, None, None, 3, Gtk.get_current_event_time())

    def on_menu_open_activate(self, menu):
        """Open the selected file."""
        folder, filename = self.get_selected_filename(self.treeview_files)
        self.open_file(os.path.join(folder, filename))

    def on_menu_goto_activate(self, menu):
        """Open the file manager in the selected file's directory."""
        folder, filename = self.get_selected_filename(self.treeview_files)
        self.open_file(folder)

    def on_menu_copy_activate(self, menu):
        """Copy the selected file name to the clipboard."""
        folder, filename = self.get_selected_filename(self.treeview_files)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(os.path.join(folder, filename), -1)
        clipboard.store()

    def on_menu_save_activate(self, menu):
        """Show a save dialog and possibly write the results to a file."""
        folder, original_file = self.get_selected_filename(self.treeview_files)
        filename = self.get_save_dialog(self.window_search, original_file)
        try:
            if os.path.exists(filename):
                if not self.get_yesno_dialog(_('The file %s already exists.  Do you '
                 + 'want to overwrite it?') % filename, self.window_search):
                    filename = None
            if filename <> None:
                try:
                    copy2(os.path.join(folder, original_file), filename)
                except Exception, msg:
                    if self.options.debug: print 'Debug:', msg
                    self.get_error_dialog(_('The file %s could not be saved.')
                     % filename, self.window_search)
        except TypeError:
            pass

    # Advanced Filters Sidebar
    def on_time_filter_custom_toggled(self, widget):
        """Enable/Disable the custom time filter button."""
        self.button_time_filter_custom.set_sensitive(widget.get_active())

    # Date Select Dialog
    def on_button_time_filter_custom_clicked(self, widget):
        """Show the Custom Time filter dialog."""
        self.date_dialog.show_all()
        self.date_dialog.run()
        self.date_dialog.hide()

    def on_calendar_start_today_toggled(self, widget):
        """Set the Start Date calendar to the current date and toggle
        sensitivity if the today checkbox is enabled."""
        if widget.get_active():
            today = datetime.datetime.now()
            self.calendar_start.select_month(today.month-1, today.year)
            self.calendar_start.select_day(today.day)
        self.calendar_start.set_sensitive(not widget.get_active())

    def on_calendar_end_today_toggled(self, widget):
        """Set the End Date calendar to the current date and toggle
        sensitivity if the today checkbox is enabled."""
        if widget.get_active():
            today = datetime.datetime.now()
            self.calendar_end.select_month(today.month-1, today.year)
            self.calendar_end.select_day(today.day)
        self.calendar_end.set_sensitive(not widget.get_active())

    def on_type_filter_other_toggled(self, widget):
        """Enable/Disable the custom file type filter button."""
        self.button_type_filter_other.set_sensitive(widget.get_active())
        self.on_filter_changed(widget)

    # Mimetypes Dialog
    def on_button_type_filter_other_clicked(self, widget):
        """Show the Custom Mimetype filter dialog."""
        self.mimetypes_dialog.show_all()
        self.mimetypes_dialog.run()
        self.mimetypes_dialog.hide()

    def on_radio_mimetype_custom_toggled(self, widget):
        """Enable/Disable mimetype selection modes."""
        self.entry_mimetype_custom.set_sensitive(widget.get_active())

    def on_radio_mimetype_existing_toggled(self, widget):
        """Enable/Disable mimetype selection modes."""
        self.combobox_mimetype_existing.set_sensitive(widget.get_active())

    # Filter Change Event
    def on_filter_changed(self, widget):
        """When a filter is changed, adjust the displayed results."""
        if self.scrolled_files.get_visible():
            self.find_in_progress = True
            if not self.options.time_iso:
                time_format = '%x %X'
            else:
                time_format = '%Y-%m-%d %H:%M'
            (keywords, folder, intersect, matchcase, hidden, limit, start_date, end_date,
             type_families, custom_mime, custom_extensions) = self.get_search_settings()
            result_filter = Filter(intersect, matchcase, hidden, start_date, end_date,
                                   time_format, type_families, custom_mime, custom_extensions)
            messages = []
            sort_settings = self.treeview_files.get_model().get_sort_column_id()
            listmodel = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, long, str)
            listmodel.set_sort_column_id(sort_settings[0], sort_settings[1])
            self.treeview_files.set_model(listmodel)
            self.treeview_files.columns_autosize()
            for filegroup in self.results:
                filename = filegroup[0]
                modification_date = filegroup[2]
                path, name = os.path.split(filename)
                (show_file, is_hidden, modification_date,
                 mime_type) = result_filter.apply_filters(filegroup, modification_date)
                if show_file:
                    listmodel.append(filegroup[4])
            if len(listmodel) == 0:
                status_icon = Gtk.STOCK_INFO
                messages.append([_('No files were found.'), None])
                status = _('No files found.')
            else:
                status = _('%s files found.') % str(len(listmodel))
            for message, action in messages:
                icon = [None, self.get_icon_pixbuf(status_icon)][message == messages[0][0]]
                listmodel.append([icon, message, None, None, action])
            self.statusbar.push(self.statusbar.get_context_id('results'), status)
            self.treeview_files.set_model(listmodel)
            listmodel.set_sort_func(4, self.compare_dates, None)

            self.window_search.get_window().set_cursor(None)
            self.find_in_progress = False


Locatefish()
Gtk.main()
