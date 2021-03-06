# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright (C) 2017 Tim Süberkrüb <dev@timsueberkrueb.io>
# Copyright (C) 2017 Dan Chapman <dpniel@ubuntu.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""The QBS plugin is useful for building parts that use the Qt Build Suite.

These are projects that are built using .qbs files and are using gcc or
clang based toolchains.

This plugin uses the common plugin keywords as well as those for "sources".
For more information check the 'plugins' topic for the former and the
'sources' topic for the latter.

Additionally, this plugin uses the following plugin-specific keywords:

    - qbs-build-variant:
      (enum, 'debug' or 'release')
      Set either debug or release build variant. Default is release.
    - qbs-options:
      (list of strings)
      Additional options to pass to the qbs invocation.
    - qbs-profile:
      (enum, 'gcc' or 'clang')
      Set either gcc or clang as the base build profile. Default is gcc.
    - qt-version:
      (enum, 'qt4' or 'qt5')
      Optionally you can set up profiles for qt4 and qt5 applications.
      If no qt version is set then the base gcc/clang profile will be used.
"""
import os
import multiprocessing
import snapcraft


class QbsPlugin(snapcraft.BasePlugin):
    @classmethod
    def schema(cls):
        schema = super().schema()

        schema['properties']['qbs-build-variant'] = {
            'enum': ['debug', 'release'],
            'default': 'release',
        }

        schema['properties']['qbs-options'] = {
            'type': 'array',
            'minitems': 1,
            'uniqueItems': True,
            'items': {
                'type': 'string',
            },
            'default': [],
        }

        schema['properties']['qbs-profile'] = {
            'enum': ['gcc', 'clang'],
            'default': 'gcc',
        }

        schema['properties']['qt-version'] = {
            'enum': ['qt4', 'qt5'],
            'default': 'qt5'
        }

        schema['properties']['qbs-jobs'] = {
            'type': 'number',
            'default': None
        }

        return schema

    @classmethod
    def get_pull_properties(cls):
        # Inform Snapcraft of the properties associated with pulling. If these
        # change in the YAML Snapcraft will consider the pull step dirty.
        return ['qt-version', 'qbs-profile']

    @classmethod
    def get_build_properties(cls):
        # Inform Snapcraft of the properties associated with building. If these
        # change in the YAML Snapcraft will consider the build step dirty.
        return ['qbs-options', 'qbs-build-variant']

    def __init__(self, name, options, project):
        super().__init__(name, options, project)
        self.build_packages.extend(['gcc'])

        if self.options.qt_version not in ('qt4', 'qt5'):
            raise RuntimeError('Unsupported Qt version: {!r}'.format(
                self.options.qt_version))

    def build(self):
        super().build()

        env = self._build_environment()

        # Setup the toolchains, there will only be gcc or clang by default
        self.run(['qbs', 'setup-toolchains', '--detect'], env=env)

        # a unique'ish name for snap builds. Hopefully this shouldn't clash
        # with any other local profiles. Each profile should look something
        # like: profiles.snapcraft-qbs-qt5-clang
        build_profile = 'snapcraft-qbs-{}-{}'.format(
            self.options.qt_version,
            self.options.qbs_profile)

        qmake = self.project.parts_dir + '/qt/install/lib/qt5/bin/qmake'

        # Setup the Qt profile.
        self.run(['qbs', 'setup-qt', qmake, build_profile], env=env)

        # Add custom search paths
        self.run([
            'qbs', 'config', 'preferences.qbsSearchPaths',
            '{}/share/qbs'.format(self.project.stage_dir)
        ], env=env)

        # Switch buildprofile to clang if required
        # we don't need to set gcc as that is the default baseProfile
        if self.options.qbs_profile == 'clang':
            self.run(['qbs', 'config',
                      'profiles.{}.baseProfile'.format(build_profile),
                      self.options.qbs_profile],
                     env=env)

        # Run the build.
        self.run(['qbs', '-v',
                  '-d', self.builddir,
                  '-f', self.sourcedir,
                  '-j', str(self.options.qbs_jobs or multiprocessing.cpu_count()),
                  self.options.qbs_build_variant,
                  'qbs.installRoot:' + self.installdir,
                  'cpp.libraryPaths:["{}","{}"]'.format(
                      '{}/lib'.format(self.project.stage_dir),
                      '{}/usr/local/lib'.format(self.project.stage_dir)
                  ),
                  'cpp.includePaths:["{}","{}","{}","{}","{}", "{}"]'.format(
                      '{}/include/KF5/Solid'.format(self.project.stage_dir),
                      '{}/include/KF5/NetworkManagerQt'.format(self.project.stage_dir),
                      '{}/include/KF5/ModemManagerQt'.format(self.project.stage_dir),
                      '{}/include/KF5/KWallet'.format(self.project.stage_dir),
                      '{}/include/KF5'.format(self.project.stage_dir),
                      '{}/usr/local/include/polkit-qt5-1'.format(self.project.stage_dir)
                  ),
                  'profile:' + build_profile] + self.options.qbs_options,
                  env=env)

    def _build_environment(self):
        env = os.environ.copy()
        if self.options.qt_version is not None:
            env['QT_SELECT'] = self.options.qt_version
        env['PKG_CONFIG_PATH'] = '{0}/usr/lib/pkgconfig:{0}/usr/lib/x86_64-linux-gnu/pkgconfig:'.format(
            self.project.stage_dir
        ) + '{0}/lib/qt5/lib/pkgconfig:{0}/lib/pkgconfig:'.format(
            self.project.stage_dir
        ) + '/usr/lib/x86_64-linux-gnu/pkgconfig'
        print(env['PKG_CONFIG_PATH'])
        env['QTDIR'] = self.project.parts_dir + '/qt/install/lib/qt5/'
        env['QML_IMPORT_PATH'] = self.project.parts_dir + '/qt/install/lib/qt5/qml'
        env['QML2_IMPORT_PATH'] = self.project.parts_dir + '/qt/install/lib/qt5/qml'
        env['LD_LIBRARY_PATH'] = self.project.parts_dir + '/qt/install/lib/qt5/lib:' + \
                                 self.project.parts_dir + '/qbs/install/usr/local/lib'
        env['PATH'] = self.project.parts_dir + '/qt/install/lib/qt5/bin/:' \
                      + self.project.parts_dir + '/qbs/install/usr/local/bin:' + \
                      os.environ["PATH"]
        return env
