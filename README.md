This is a fork of catfish 0.4 (https://launchpad.net/catfish-search/0.4). I forked 0.4 instead
of 0.6 simply because I don't like the way 0.6 looks (due to GTK3?). I've changed several
things to my own liking. Maybe you'll like them too, or use them as a guide to make your own
changes:

* change default search folder
* change the column order
* increase window size
* speed up search by disabling word suggestions
* speed up search by limiting "locate" command to currently selected folder
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
