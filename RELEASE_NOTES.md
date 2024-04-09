Release Notes for Show in File Manager 1.1.6
============================================

 - Show in File Manager 1.1.6 switches its build system from `setuptools` to 
   [Hatch](https://github.com/pypa/hatch).

 - To generate the manpage, a new plugin [Hatch-argparse-manpage](https://github.com/damonlynch/hatch-argparse-manpage) 
   is used, which is a new build-time dependency. Tthis plugin can be used 
   with any Hatch project, not just Show in File Manager. 
