# -*- coding: UTF-8 -*-
# Copyright (C) 2005-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2006-2007 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2008 Henry Obein <henry@itaapy.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Import from the Standard Library
from subprocess import Popen, PIPE

# Import from itools
from itools.datatypes import DateTime, String
from itools.gettext import MSG
from itools import git
from itools.i18n import format_datetime
from itools.web import get_context, STLView
from itools.xapian import KeywordField, BoolField

# Import from ikaaro
from file import File
from metadata import Record



###########################################################################
# Views
###########################################################################
class HistoryView(STLView):

    access = 'is_allowed_to_view'
    title = MSG(u'History')
    icon = 'history.png'
    template = '/ui/file/history.xml'


    def get_namespace(self, resource, context):
        # Change the dates
        accept = context.accept_language
        revisions = resource.get_revisions(context)
        for revision in revisions:
            date = revision['date']
            revision['date'] = format_datetime(date, accept=accept)

        return {'revisions': revisions}



###########################################################################
# Model
###########################################################################
class History(Record):

    schema = {
        'date': DateTime,
        'user': String,
        'size': String}


class VersioningAware(File):

    class_version = '20090119'

    def get_revisions(self, context=None):
        if context is None:
            context = get_context()

        # Get the list of revisions
        command = ['git', 'rev-list', 'HEAD', '--']
        for handler in self.get_handlers():
            path = str(handler.uri.path)
            command.append(path)
        cwd = context.server.database.path
        pipe = Popen(command, cwd=cwd, stdout=PIPE).stdout

        # Get the metadata
        revisions = []
        for line in pipe.readlines():
            line = line.strip()
            metadata = git.get_metadata(line, cwd=cwd)
            date = metadata['committer'][1]
            username = metadata['message'].strip()
            revisions.append({
                'username': username,
                'date': date})

        return revisions


    def get_owner(self):
        revisions = self.get_revisions()
        if not revisions:
            return None
        return revisions[-1]['username']


    def get_last_author(self):
        revisions = self.get_revisions()
        if not revisions:
            return None
        return revisions[0]['username']


    def get_mtime(self):
        revisions = self.get_revisions()
        if not revisions:
            return File.get_mtime(self)
        return revisions[0]['date']


    ########################################################################
    # Index & Search
    ########################################################################
    def get_catalog_fields(self):
        return File.get_catalog_fields(self) + [
            # Versioning Aware
            BoolField('is_version_aware'),
            KeywordField('last_author', is_indexed=False, is_stored=True)]


    def get_catalog_values(self):
        document = File.get_catalog_values(self)

        document['is_version_aware'] = True
        # Last Author (used in the Last Changes view)
        last_author = self.get_last_author()
        if last_author is not None:
            users = self.get_resource('/users')
            try:
                user = users.get_resource(last_author)
            except LookupError:
                document['last_author'] = None
            else:
                document['last_author'] = user.get_title()

        return document


    ########################################################################
    # User Interface
    ########################################################################
    history = HistoryView()


    ########################################################################
    # Update
    ########################################################################
    def update_20090119(self):
        get_context().server.database.add_resource(self)
