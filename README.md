[locatefish](https://github.com/locatefish) is a simple GUI for "locate", forked from [catfish
0.4] (https://launchpad.net/catfish-search/0.4). I forked 0.4 instead of 0.6 simply because I
prefer the way it looks.

Besides limiting it to "locate", I've changed several other things to my own liking. Maybe
you'll like them too, or use them as a guide to make your own changes:

* remove all search methods other than "locate"
* optionally intersect (AND) results from search terms instead of taking their union (OR)
* speed up search by removing word suggestions
* disable regexps to allow limiting "locate" command to selected folder
* speed up search by limiting "locate" command to selected folder
* change default search folder
* change the column order
* increase window size
* use ISO time format, and show local time instead of UTC

Martin Spacek <git@mspacek.mm.st>

===============

Original README:

Catfish is a handy file searching tool for linux and unix. Basically it is a frontend for
different search engines (daemons) which provides a unified interface. The interface is
intentionally lightweight and simple, using only GTK+3. You can configure it to your needs by
using several command line options.

Supported backends are find, (s)locate, doodle, tracker, strigi and pinot.

Dependencies: python-gi, python-xdg, dbus (for strigi and pinot)

For installation instructions read INSTALL.
For questions about the search backends please read their specific manuals.

You are encouraged to run 'catfish --help' to check out the various command line options.

Please report comments, suggestions and bugs to:
    Christian Dywan <christian@twotoasts.de>

Check for new versions at:
    www.twotoasts.de
