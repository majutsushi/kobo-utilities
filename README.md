# Kobo Utilities

## Overview

This is a plugin for the [Calibre Ebook reader](https://calibre-ebook.com/)
that provides additional functionality when working with Kobo eReaders.

It was originally written by [David Forrester](https://github.com/davidfor)
and is now maintained by me.

The main homepage for the plugin is the thread on the MobileRead Forum:
<https://www.mobileread.com/forums/showthread.php?t=366110>

## Contributing

Contributions are always welcome.

The `scripts/run` tool is the main way to build and test the plugin.
It can run various tasks:

- `scripts/run build`: Build the plugin.
  This will produce a file `KoboUtilities-vX.Y.Z[suffix].zip` in the repo root
  that can be installed in Calibre.
- `scripts/run update-calibre`: Download the earliest supported and latest versions
  of Calibre to use for tests.
  This currently only works on Linux.
- `scripts/run test`: Build the plugin, update Calibre if necessary,
  and then run the tests in `tests`.
- `scripts/run install`: Build and install the plugin in Calibre.
- `scripts/run install-and-debug`: Build and install the plugin in Calibre,
  and then start Calibre in debug mode.

Note that `calibre-customize -b .` will not work due to the project structure
being different from how that command expects it.

The project uses pyright for type checking and ruff for linting and formatting,
so please make sure to run those tools before submitting a pull request.
