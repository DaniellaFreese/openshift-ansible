#!/usr/bin/env python
# pylint: disable=missing-docstring
# flake8: noqa: T001
#     ___ ___ _  _ ___ ___    _ _____ ___ ___
#    / __| __| \| | __| _ \  /_\_   _| __|   \
#   | (_ | _|| .` | _||   / / _ \| | | _|| |) |
#    \___|___|_|\_|___|_|_\/_/_\_\_|_|___|___/_ _____
#   |   \ / _ \  | \| |/ _ \_   _| | __|   \_ _|_   _|
#   | |) | (_) | | .` | (_) || |   | _|| |) | |  | |
#   |___/ \___/  |_|\_|\___/ |_|   |___|___/___| |_|
#
# Copyright 2016 Red Hat, Inc. and/or its affiliates
# and other contributors as indicated by the @author tags.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# -*- -*- -*- Begin included fragment: lib/import.py -*- -*- -*-
'''
   OpenShiftCLI class that wraps the oc commands in a subprocess
'''
# pylint: disable=too-many-lines

from __future__ import print_function
import atexit
import copy
import json
import os
import re
import shutil
import subprocess
import tempfile
# pylint: disable=import-error
try:
    import ruamel.yaml as yaml
except ImportError:
    import yaml

from ansible.module_utils.basic import AnsibleModule

# -*- -*- -*- End included fragment: lib/import.py -*- -*- -*-

# -*- -*- -*- Begin included fragment: doc/sdnvalidator -*- -*- -*-

DOCUMENTATION = '''
---
module: oc_sdnvalidator
short_description: Validate SDN objects
description:
  - Validate SDN objects
options:
  kubeconfig:
    description:
    - The path for the kubeconfig file to use for authentication
    required: false
    default: /etc/origin/master/admin.kubeconfig
    aliases: []
author:
- "Mo Khan <monis@redhat.com>"
extends_documentation_fragment: []
'''

EXAMPLES = '''
oc_version:
- name: get oc sdnvalidator
  sdnvalidator:
  register: oc_sdnvalidator
'''

# -*- -*- -*- End included fragment: doc/sdnvalidator -*- -*- -*-

# -*- -*- -*- Begin included fragment: ../../lib_utils/src/class/yedit.py -*- -*- -*-
# pylint: disable=undefined-variable,missing-docstring
# noqa: E301,E302


class YeditException(Exception):
    ''' Exception class for Yedit '''
    pass


# pylint: disable=too-many-public-methods
class Yedit(object):
    ''' Class to modify yaml files '''
    re_valid_key = r"(((\[-?\d+\])|([0-9a-zA-Z%s/_-]+)).?)+$"
    re_key = r"(?:\[(-?\d+)\])|([0-9a-zA-Z%s/_-]+)"
    com_sep = set(['.', '#', '|', ':'])

    # pylint: disable=too-many-arguments
    def __init__(self,
                 filename=None,
                 content=None,
                 content_type='yaml',
                 separator='.',
                 backup=False):
        self.content = content
        self._separator = separator
        self.filename = filename
        self.__yaml_dict = content
        self.content_type = content_type
        self.backup = backup
        self.load(content_type=self.content_type)
        if self.__yaml_dict is None:
            self.__yaml_dict = {}

    @property
    def separator(self):
        ''' getter method for yaml_dict '''
        return self._separator

    @separator.setter
    def separator(self):
        ''' getter method for yaml_dict '''
        return self._separator

    @property
    def yaml_dict(self):
        ''' getter method for yaml_dict '''
        return self.__yaml_dict

    @yaml_dict.setter
    def yaml_dict(self, value):
        ''' setter method for yaml_dict '''
        self.__yaml_dict = value

    @staticmethod
    def parse_key(key, sep='.'):
        '''parse the key allowing the appropriate separator'''
        common_separators = list(Yedit.com_sep - set([sep]))
        return re.findall(Yedit.re_key % ''.join(common_separators), key)

    @staticmethod
    def valid_key(key, sep='.'):
        '''validate the incoming key'''
        common_separators = list(Yedit.com_sep - set([sep]))
        if not re.match(Yedit.re_valid_key % ''.join(common_separators), key):
            return False

        return True

    @staticmethod
    def remove_entry(data, key, sep='.'):
        ''' remove data at location key '''
        if key == '' and isinstance(data, dict):
            data.clear()
            return True
        elif key == '' and isinstance(data, list):
            del data[:]
            return True

        if not (key and Yedit.valid_key(key, sep)) and \
           isinstance(data, (list, dict)):
            return None

        key_indexes = Yedit.parse_key(key, sep)
        for arr_ind, dict_key in key_indexes[:-1]:
            if dict_key and isinstance(data, dict):
                data = data.get(dict_key, None)
            elif (arr_ind and isinstance(data, list) and
                  int(arr_ind) <= len(data) - 1):
                data = data[int(arr_ind)]
            else:
                return None

        # process last index for remove
        # expected list entry
        if key_indexes[-1][0]:
            if isinstance(data, list) and int(key_indexes[-1][0]) <= len(data) - 1:  # noqa: E501
                del data[int(key_indexes[-1][0])]
                return True

        # expected dict entry
        elif key_indexes[-1][1]:
            if isinstance(data, dict):
                del data[key_indexes[-1][1]]
                return True

    @staticmethod
    def add_entry(data, key, item=None, sep='.'):
        ''' Get an item from a dictionary with key notation a.b.c
            d = {'a': {'b': 'c'}}}
            key = a#b
            return c
        '''
        if key == '':
            pass
        elif (not (key and Yedit.valid_key(key, sep)) and
              isinstance(data, (list, dict))):
            return None

        key_indexes = Yedit.parse_key(key, sep)
        for arr_ind, dict_key in key_indexes[:-1]:
            if dict_key:
                if isinstance(data, dict) and dict_key in data and data[dict_key]:  # noqa: E501
                    data = data[dict_key]
                    continue

                elif data and not isinstance(data, dict):
                    raise YeditException("Unexpected item type found while going through key " +
                                         "path: {} (at key: {})".format(key, dict_key))

                data[dict_key] = {}
                data = data[dict_key]

            elif (arr_ind and isinstance(data, list) and
                  int(arr_ind) <= len(data) - 1):
                data = data[int(arr_ind)]
            else:
                raise YeditException("Unexpected item type found while going through key path: {}".format(key))

        if key == '':
            data = item

        # process last index for add
        # expected list entry
        elif key_indexes[-1][0] and isinstance(data, list) and int(key_indexes[-1][0]) <= len(data) - 1:  # noqa: E501
            data[int(key_indexes[-1][0])] = item

        # expected dict entry
        elif key_indexes[-1][1] and isinstance(data, dict):
            data[key_indexes[-1][1]] = item

        # didn't add/update to an existing list, nor add/update key to a dict
        # so we must have been provided some syntax like a.b.c[<int>] = "data" for a
        # non-existent array
        else:
            raise YeditException("Error adding to object at path: {}".format(key))

        return data

    @staticmethod
    def get_entry(data, key, sep='.'):
        ''' Get an item from a dictionary with key notation a.b.c
            d = {'a': {'b': 'c'}}}
            key = a.b
            return c
        '''
        if key == '':
            pass
        elif (not (key and Yedit.valid_key(key, sep)) and
              isinstance(data, (list, dict))):
            return None

        key_indexes = Yedit.parse_key(key, sep)
        for arr_ind, dict_key in key_indexes:
            if dict_key and isinstance(data, dict):
                data = data.get(dict_key, None)
            elif (arr_ind and isinstance(data, list) and
                  int(arr_ind) <= len(data) - 1):
                data = data[int(arr_ind)]
            else:
                return None

        return data

    @staticmethod
    def _write(filename, contents):
        ''' Actually write the file contents to disk. This helps with mocking. '''

        tmp_filename = filename + '.yedit'

        with open(tmp_filename, 'w') as yfd:
            yfd.write(contents)

        os.rename(tmp_filename, filename)

    def write(self):
        ''' write to file '''
        if not self.filename:
            raise YeditException('Please specify a filename.')

        if self.backup and self.file_exists():
            shutil.copy(self.filename, self.filename + '.orig')

        # Try to set format attributes if supported
        try:
            self.yaml_dict.fa.set_block_style()
        except AttributeError:
            pass

        # Try to use RoundTripDumper if supported.
        try:
            Yedit._write(self.filename, yaml.dump(self.yaml_dict, Dumper=yaml.RoundTripDumper))
        except AttributeError:
            Yedit._write(self.filename, yaml.safe_dump(self.yaml_dict, default_flow_style=False))

        return (True, self.yaml_dict)

    def read(self):
        ''' read from file '''
        # check if it exists
        if self.filename is None or not self.file_exists():
            return None

        contents = None
        with open(self.filename) as yfd:
            contents = yfd.read()

        return contents

    def file_exists(self):
        ''' return whether file exists '''
        if os.path.exists(self.filename):
            return True

        return False

    def load(self, content_type='yaml'):
        ''' return yaml file '''
        contents = self.read()

        if not contents and not self.content:
            return None

        if self.content:
            if isinstance(self.content, dict):
                self.yaml_dict = self.content
                return self.yaml_dict
            elif isinstance(self.content, str):
                contents = self.content

        # check if it is yaml
        try:
            if content_type == 'yaml' and contents:
                # Try to set format attributes if supported
                try:
                    self.yaml_dict.fa.set_block_style()
                except AttributeError:
                    pass

                # Try to use RoundTripLoader if supported.
                try:
                    self.yaml_dict = yaml.safe_load(contents, yaml.RoundTripLoader)
                except AttributeError:
                    self.yaml_dict = yaml.safe_load(contents)

                # Try to set format attributes if supported
                try:
                    self.yaml_dict.fa.set_block_style()
                except AttributeError:
                    pass

            elif content_type == 'json' and contents:
                self.yaml_dict = json.loads(contents)
        except yaml.YAMLError as err:
            # Error loading yaml or json
            raise YeditException('Problem with loading yaml file. %s' % err)

        return self.yaml_dict

    def get(self, key):
        ''' get a specified key'''
        try:
            entry = Yedit.get_entry(self.yaml_dict, key, self.separator)
        except KeyError:
            entry = None

        return entry

    def pop(self, path, key_or_item):
        ''' remove a key, value pair from a dict or an item for a list'''
        try:
            entry = Yedit.get_entry(self.yaml_dict, path, self.separator)
        except KeyError:
            entry = None

        if entry is None:
            return (False, self.yaml_dict)

        if isinstance(entry, dict):
            # AUDIT:maybe-no-member makes sense due to fuzzy types
            # pylint: disable=maybe-no-member
            if key_or_item in entry:
                entry.pop(key_or_item)
                return (True, self.yaml_dict)
            return (False, self.yaml_dict)

        elif isinstance(entry, list):
            # AUDIT:maybe-no-member makes sense due to fuzzy types
            # pylint: disable=maybe-no-member
            ind = None
            try:
                ind = entry.index(key_or_item)
            except ValueError:
                return (False, self.yaml_dict)

            entry.pop(ind)
            return (True, self.yaml_dict)

        return (False, self.yaml_dict)

    def delete(self, path):
        ''' remove path from a dict'''
        try:
            entry = Yedit.get_entry(self.yaml_dict, path, self.separator)
        except KeyError:
            entry = None

        if entry is None:
            return (False, self.yaml_dict)

        result = Yedit.remove_entry(self.yaml_dict, path, self.separator)
        if not result:
            return (False, self.yaml_dict)

        return (True, self.yaml_dict)

    def exists(self, path, value):
        ''' check if value exists at path'''
        try:
            entry = Yedit.get_entry(self.yaml_dict, path, self.separator)
        except KeyError:
            entry = None

        if isinstance(entry, list):
            if value in entry:
                return True
            return False

        elif isinstance(entry, dict):
            if isinstance(value, dict):
                rval = False
                for key, val in value.items():
                    if entry[key] != val:
                        rval = False
                        break
                else:
                    rval = True
                return rval

            return value in entry

        return entry == value

    def append(self, path, value):
        '''append value to a list'''
        try:
            entry = Yedit.get_entry(self.yaml_dict, path, self.separator)
        except KeyError:
            entry = None

        if entry is None:
            self.put(path, [])
            entry = Yedit.get_entry(self.yaml_dict, path, self.separator)
        if not isinstance(entry, list):
            return (False, self.yaml_dict)

        # AUDIT:maybe-no-member makes sense due to loading data from
        # a serialized format.
        # pylint: disable=maybe-no-member
        entry.append(value)
        return (True, self.yaml_dict)

    # pylint: disable=too-many-arguments
    def update(self, path, value, index=None, curr_value=None):
        ''' put path, value into a dict '''
        try:
            entry = Yedit.get_entry(self.yaml_dict, path, self.separator)
        except KeyError:
            entry = None

        if isinstance(entry, dict):
            # AUDIT:maybe-no-member makes sense due to fuzzy types
            # pylint: disable=maybe-no-member
            if not isinstance(value, dict):
                raise YeditException('Cannot replace key, value entry in ' +
                                     'dict with non-dict type. value=[%s] [%s]' % (value, type(value)))  # noqa: E501

            entry.update(value)
            return (True, self.yaml_dict)

        elif isinstance(entry, list):
            # AUDIT:maybe-no-member makes sense due to fuzzy types
            # pylint: disable=maybe-no-member
            ind = None
            if curr_value:
                try:
                    ind = entry.index(curr_value)
                except ValueError:
                    return (False, self.yaml_dict)

            elif index is not None:
                ind = index

            if ind is not None and entry[ind] != value:
                entry[ind] = value
                return (True, self.yaml_dict)

            # see if it exists in the list
            try:
                ind = entry.index(value)
            except ValueError:
                # doesn't exist, append it
                entry.append(value)
                return (True, self.yaml_dict)

            # already exists, return
            if ind is not None:
                return (False, self.yaml_dict)
        return (False, self.yaml_dict)

    def put(self, path, value):
        ''' put path, value into a dict '''
        try:
            entry = Yedit.get_entry(self.yaml_dict, path, self.separator)
        except KeyError:
            entry = None

        if entry == value:
            return (False, self.yaml_dict)

        # deepcopy didn't work
        # Try to use ruamel.yaml and fallback to pyyaml
        try:
            tmp_copy = yaml.load(yaml.round_trip_dump(self.yaml_dict,
                                                      default_flow_style=False),
                                 yaml.RoundTripLoader)
        except AttributeError:
            tmp_copy = copy.deepcopy(self.yaml_dict)

        # set the format attributes if available
        try:
            tmp_copy.fa.set_block_style()
        except AttributeError:
            pass

        result = Yedit.add_entry(tmp_copy, path, value, self.separator)
        if not result:
            return (False, self.yaml_dict)

        self.yaml_dict = tmp_copy

        return (True, self.yaml_dict)

    def create(self, path, value):
        ''' create a yaml file '''
        if not self.file_exists():
            # deepcopy didn't work
            # Try to use ruamel.yaml and fallback to pyyaml
            try:
                tmp_copy = yaml.load(yaml.round_trip_dump(self.yaml_dict,
                                                          default_flow_style=False),
                                     yaml.RoundTripLoader)
            except AttributeError:
                tmp_copy = copy.deepcopy(self.yaml_dict)

            # set the format attributes if available
            try:
                tmp_copy.fa.set_block_style()
            except AttributeError:
                pass

            result = Yedit.add_entry(tmp_copy, path, value, self.separator)
            if result:
                self.yaml_dict = tmp_copy
                return (True, self.yaml_dict)

        return (False, self.yaml_dict)

    @staticmethod
    def get_curr_value(invalue, val_type):
        '''return the current value'''
        if invalue is None:
            return None

        curr_value = invalue
        if val_type == 'yaml':
            curr_value = yaml.load(invalue)
        elif val_type == 'json':
            curr_value = json.loads(invalue)

        return curr_value

    @staticmethod
    def parse_value(inc_value, vtype=''):
        '''determine value type passed'''
        true_bools = ['y', 'Y', 'yes', 'Yes', 'YES', 'true', 'True', 'TRUE',
                      'on', 'On', 'ON', ]
        false_bools = ['n', 'N', 'no', 'No', 'NO', 'false', 'False', 'FALSE',
                       'off', 'Off', 'OFF']

        # It came in as a string but you didn't specify value_type as string
        # we will convert to bool if it matches any of the above cases
        if isinstance(inc_value, str) and 'bool' in vtype:
            if inc_value not in true_bools and inc_value not in false_bools:
                raise YeditException('Not a boolean type. str=[%s] vtype=[%s]'
                                     % (inc_value, vtype))
        elif isinstance(inc_value, bool) and 'str' in vtype:
            inc_value = str(inc_value)

        # If vtype is not str then go ahead and attempt to yaml load it.
        if isinstance(inc_value, str) and 'str' not in vtype:
            try:
                inc_value = yaml.load(inc_value)
            except Exception:
                raise YeditException('Could not determine type of incoming ' +
                                     'value. value=[%s] vtype=[%s]'
                                     % (type(inc_value), vtype))

        return inc_value

    # pylint: disable=too-many-return-statements,too-many-branches
    @staticmethod
    def run_ansible(module):
        '''perform the idempotent crud operations'''
        yamlfile = Yedit(filename=module.params['src'],
                         backup=module.params['backup'],
                         separator=module.params['separator'])

        if module.params['src']:
            rval = yamlfile.load()

            if yamlfile.yaml_dict is None and \
               module.params['state'] != 'present':
                return {'failed': True,
                        'msg': 'Error opening file [%s].  Verify that the ' +
                               'file exists, that it is has correct' +
                               ' permissions, and is valid yaml.'}

        if module.params['state'] == 'list':
            if module.params['content']:
                content = Yedit.parse_value(module.params['content'],
                                            module.params['content_type'])
                yamlfile.yaml_dict = content

            if module.params['key']:
                rval = yamlfile.get(module.params['key']) or {}

            return {'changed': False, 'result': rval, 'state': "list"}

        elif module.params['state'] == 'absent':
            if module.params['content']:
                content = Yedit.parse_value(module.params['content'],
                                            module.params['content_type'])
                yamlfile.yaml_dict = content

            if module.params['update']:
                rval = yamlfile.pop(module.params['key'],
                                    module.params['value'])
            else:
                rval = yamlfile.delete(module.params['key'])

            if rval[0] and module.params['src']:
                yamlfile.write()

            return {'changed': rval[0], 'result': rval[1], 'state': "absent"}

        elif module.params['state'] == 'present':
            # check if content is different than what is in the file
            if module.params['content']:
                content = Yedit.parse_value(module.params['content'],
                                            module.params['content_type'])

                # We had no edits to make and the contents are the same
                if yamlfile.yaml_dict == content and \
                   module.params['value'] is None:
                    return {'changed': False,
                            'result': yamlfile.yaml_dict,
                            'state': "present"}

                yamlfile.yaml_dict = content

            # we were passed a value; parse it
            if module.params['value']:
                value = Yedit.parse_value(module.params['value'],
                                          module.params['value_type'])
                key = module.params['key']
                if module.params['update']:
                    # pylint: disable=line-too-long
                    curr_value = Yedit.get_curr_value(Yedit.parse_value(module.params['curr_value']),  # noqa: E501
                                                      module.params['curr_value_format'])  # noqa: E501

                    rval = yamlfile.update(key, value, module.params['index'], curr_value)  # noqa: E501

                elif module.params['append']:
                    rval = yamlfile.append(key, value)
                else:
                    rval = yamlfile.put(key, value)

                if rval[0] and module.params['src']:
                    yamlfile.write()

                return {'changed': rval[0],
                        'result': rval[1], 'state': "present"}

            # no edits to make
            if module.params['src']:
                # pylint: disable=redefined-variable-type
                rval = yamlfile.write()
                return {'changed': rval[0],
                        'result': rval[1],
                        'state': "present"}

        return {'failed': True, 'msg': 'Unkown state passed'}

# -*- -*- -*- End included fragment: ../../lib_utils/src/class/yedit.py -*- -*- -*-

# -*- -*- -*- Begin included fragment: lib/base.py -*- -*- -*-
# pylint: disable=too-many-lines
# noqa: E301,E302,E303,T001


class OpenShiftCLIError(Exception):
    '''Exception class for openshiftcli'''
    pass


ADDITIONAL_PATH_LOOKUPS = ['/usr/local/bin', os.path.expanduser('~/bin')]


def locate_oc_binary():
    ''' Find and return oc binary file '''
    # https://github.com/openshift/openshift-ansible/issues/3410
    # oc can be in /usr/local/bin in some cases, but that may not
    # be in $PATH due to ansible/sudo
    paths = os.environ.get("PATH", os.defpath).split(os.pathsep) + ADDITIONAL_PATH_LOOKUPS

    oc_binary = 'oc'

    # Use shutil.which if it is available, otherwise fallback to a naive path search
    try:
        which_result = shutil.which(oc_binary, path=os.pathsep.join(paths))
        if which_result is not None:
            oc_binary = which_result
    except AttributeError:
        for path in paths:
            if os.path.exists(os.path.join(path, oc_binary)):
                oc_binary = os.path.join(path, oc_binary)
                break

    return oc_binary


# pylint: disable=too-few-public-methods
class OpenShiftCLI(object):
    ''' Class to wrap the command line tools '''
    def __init__(self,
                 namespace,
                 kubeconfig='/etc/origin/master/admin.kubeconfig',
                 verbose=False,
                 all_namespaces=False):
        ''' Constructor for OpenshiftCLI '''
        self.namespace = namespace
        self.verbose = verbose
        self.kubeconfig = Utils.create_tmpfile_copy(kubeconfig)
        self.all_namespaces = all_namespaces
        self.oc_binary = locate_oc_binary()

    # Pylint allows only 5 arguments to be passed.
    # pylint: disable=too-many-arguments
    def _replace_content(self, resource, rname, content, force=False, sep='.'):
        ''' replace the current object with the content '''
        res = self._get(resource, rname)
        if not res['results']:
            return res

        fname = Utils.create_tmpfile(rname + '-')

        yed = Yedit(fname, res['results'][0], separator=sep)
        changes = []
        for key, value in content.items():
            changes.append(yed.put(key, value))

        if any([change[0] for change in changes]):
            yed.write()

            atexit.register(Utils.cleanup, [fname])

            return self._replace(fname, force)

        return {'returncode': 0, 'updated': False}

    def _replace(self, fname, force=False):
        '''replace the current object with oc replace'''
        cmd = ['replace', '-f', fname]
        if force:
            cmd.append('--force')
        return self.openshift_cmd(cmd)

    def _create_from_content(self, rname, content):
        '''create a temporary file and then call oc create on it'''
        fname = Utils.create_tmpfile(rname + '-')
        yed = Yedit(fname, content=content)
        yed.write()

        atexit.register(Utils.cleanup, [fname])

        return self._create(fname)

    def _create(self, fname):
        '''call oc create on a filename'''
        return self.openshift_cmd(['create', '-f', fname])

    def _delete(self, resource, rname, selector=None):
        '''call oc delete on a resource'''
        cmd = ['delete', resource, rname]
        if selector:
            cmd.append('--selector=%s' % selector)

        return self.openshift_cmd(cmd)

    def _process(self, template_name, create=False, params=None, template_data=None):  # noqa: E501
        '''process a template

           template_name: the name of the template to process
           create: whether to send to oc create after processing
           params: the parameters for the template
           template_data: the incoming template's data; instead of a file
        '''
        cmd = ['process']
        if template_data:
            cmd.extend(['-f', '-'])
        else:
            cmd.append(template_name)
        if params:
            param_str = ["%s=%s" % (key, value) for key, value in params.items()]
            cmd.append('-v')
            cmd.extend(param_str)

        results = self.openshift_cmd(cmd, output=True, input_data=template_data)

        if results['returncode'] != 0 or not create:
            return results

        fname = Utils.create_tmpfile(template_name + '-')
        yed = Yedit(fname, results['results'])
        yed.write()

        atexit.register(Utils.cleanup, [fname])

        return self.openshift_cmd(['create', '-f', fname])

    def _get(self, resource, rname=None, selector=None):
        '''return a resource by name '''
        cmd = ['get', resource]
        if selector:
            cmd.append('--selector=%s' % selector)
        elif rname:
            cmd.append(rname)

        cmd.extend(['-o', 'json'])

        rval = self.openshift_cmd(cmd, output=True)

        # Ensure results are retuned in an array
        if 'items' in rval:
            rval['results'] = rval['items']
        elif not isinstance(rval['results'], list):
            rval['results'] = [rval['results']]

        return rval

    def _schedulable(self, node=None, selector=None, schedulable=True):
        ''' perform oadm manage-node scheduable '''
        cmd = ['manage-node']
        if node:
            cmd.extend(node)
        else:
            cmd.append('--selector=%s' % selector)

        cmd.append('--schedulable=%s' % schedulable)

        return self.openshift_cmd(cmd, oadm=True, output=True, output_type='raw')  # noqa: E501

    def _list_pods(self, node=None, selector=None, pod_selector=None):
        ''' perform oadm list pods

            node: the node in which to list pods
            selector: the label selector filter if provided
            pod_selector: the pod selector filter if provided
        '''
        cmd = ['manage-node']
        if node:
            cmd.extend(node)
        else:
            cmd.append('--selector=%s' % selector)

        if pod_selector:
            cmd.append('--pod-selector=%s' % pod_selector)

        cmd.extend(['--list-pods', '-o', 'json'])

        return self.openshift_cmd(cmd, oadm=True, output=True, output_type='raw')

    # pylint: disable=too-many-arguments
    def _evacuate(self, node=None, selector=None, pod_selector=None, dry_run=False, grace_period=None, force=False):
        ''' perform oadm manage-node evacuate '''
        cmd = ['manage-node']
        if node:
            cmd.extend(node)
        else:
            cmd.append('--selector=%s' % selector)

        if dry_run:
            cmd.append('--dry-run')

        if pod_selector:
            cmd.append('--pod-selector=%s' % pod_selector)

        if grace_period:
            cmd.append('--grace-period=%s' % int(grace_period))

        if force:
            cmd.append('--force')

        cmd.append('--evacuate')

        return self.openshift_cmd(cmd, oadm=True, output=True, output_type='raw')

    def _version(self):
        ''' return the openshift version'''
        return self.openshift_cmd(['version'], output=True, output_type='raw')

    def _import_image(self, url=None, name=None, tag=None):
        ''' perform image import '''
        cmd = ['import-image']

        image = '{0}'.format(name)
        if tag:
            image += ':{0}'.format(tag)

        cmd.append(image)

        if url:
            cmd.append('--from={0}/{1}'.format(url, image))

        cmd.append('-n{0}'.format(self.namespace))

        cmd.append('--confirm')
        return self.openshift_cmd(cmd)

    def _run(self, cmds, input_data):
        ''' Actually executes the command. This makes mocking easier. '''
        curr_env = os.environ.copy()
        curr_env.update({'KUBECONFIG': self.kubeconfig})
        proc = subprocess.Popen(cmds,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=curr_env)

        stdout, stderr = proc.communicate(input_data)

        return proc.returncode, stdout.decode(), stderr.decode()

    # pylint: disable=too-many-arguments,too-many-branches
    def openshift_cmd(self, cmd, oadm=False, output=False, output_type='json', input_data=None):
        '''Base command for oc '''
        cmds = [self.oc_binary]

        if oadm:
            cmds.append('adm')

        cmds.extend(cmd)

        if self.all_namespaces:
            cmds.extend(['--all-namespaces'])
        elif self.namespace is not None and self.namespace.lower() not in ['none', 'emtpy']:  # E501
            cmds.extend(['-n', self.namespace])

        rval = {}
        results = ''
        err = None

        if self.verbose:
            print(' '.join(cmds))

        try:
            returncode, stdout, stderr = self._run(cmds, input_data)
        except OSError as ex:
            returncode, stdout, stderr = 1, '', 'Failed to execute {}: {}'.format(subprocess.list2cmdline(cmds), ex)

        rval = {"returncode": returncode,
                "results": results,
                "cmd": ' '.join(cmds)}

        if returncode == 0:
            if output:
                if output_type == 'json':
                    try:
                        rval['results'] = json.loads(stdout)
                    except ValueError as err:
                        if "No JSON object could be decoded" in err.args:
                            err = err.args
                elif output_type == 'raw':
                    rval['results'] = stdout

            if self.verbose:
                print("STDOUT: {0}".format(stdout))
                print("STDERR: {0}".format(stderr))

            if err:
                rval.update({"err": err,
                             "stderr": stderr,
                             "stdout": stdout,
                             "cmd": cmds})

        else:
            rval.update({"stderr": stderr,
                         "stdout": stdout,
                         "results": {}})

        return rval


class Utils(object):
    ''' utilities for openshiftcli modules '''

    @staticmethod
    def _write(filename, contents):
        ''' Actually write the file contents to disk. This helps with mocking. '''

        with open(filename, 'w') as sfd:
            sfd.write(contents)

    @staticmethod
    def create_tmp_file_from_contents(rname, data, ftype='yaml'):
        ''' create a file in tmp with name and contents'''

        tmp = Utils.create_tmpfile(prefix=rname)

        if ftype == 'yaml':
            # AUDIT:no-member makes sense here due to ruamel.YAML/PyYAML usage
            # pylint: disable=no-member
            if hasattr(yaml, 'RoundTripDumper'):
                Utils._write(tmp, yaml.dump(data, Dumper=yaml.RoundTripDumper))
            else:
                Utils._write(tmp, yaml.safe_dump(data, default_flow_style=False))

        elif ftype == 'json':
            Utils._write(tmp, json.dumps(data))
        else:
            Utils._write(tmp, data)

        # Register cleanup when module is done
        atexit.register(Utils.cleanup, [tmp])
        return tmp

    @staticmethod
    def create_tmpfile_copy(inc_file):
        '''create a temporary copy of a file'''
        tmpfile = Utils.create_tmpfile('lib_openshift-')
        Utils._write(tmpfile, open(inc_file).read())

        # Cleanup the tmpfile
        atexit.register(Utils.cleanup, [tmpfile])

        return tmpfile

    @staticmethod
    def create_tmpfile(prefix='tmp'):
        ''' Generates and returns a temporary file name '''

        with tempfile.NamedTemporaryFile(prefix=prefix, delete=False) as tmp:
            return tmp.name

    @staticmethod
    def create_tmp_files_from_contents(content, content_type=None):
        '''Turn an array of dict: filename, content into a files array'''
        if not isinstance(content, list):
            content = [content]
        files = []
        for item in content:
            path = Utils.create_tmp_file_from_contents(item['path'] + '-',
                                                       item['data'],
                                                       ftype=content_type)
            files.append({'name': os.path.basename(item['path']),
                          'path': path})
        return files

    @staticmethod
    def cleanup(files):
        '''Clean up on exit '''
        for sfile in files:
            if os.path.exists(sfile):
                if os.path.isdir(sfile):
                    shutil.rmtree(sfile)
                elif os.path.isfile(sfile):
                    os.remove(sfile)

    @staticmethod
    def exists(results, _name):
        ''' Check to see if the results include the name '''
        if not results:
            return False

        if Utils.find_result(results, _name):
            return True

        return False

    @staticmethod
    def find_result(results, _name):
        ''' Find the specified result by name'''
        rval = None
        for result in results:
            if 'metadata' in result and result['metadata']['name'] == _name:
                rval = result
                break

        return rval

    @staticmethod
    def get_resource_file(sfile, sfile_type='yaml'):
        ''' return the service file '''
        contents = None
        with open(sfile) as sfd:
            contents = sfd.read()

        if sfile_type == 'yaml':
            # AUDIT:no-member makes sense here due to ruamel.YAML/PyYAML usage
            # pylint: disable=no-member
            if hasattr(yaml, 'RoundTripLoader'):
                contents = yaml.load(contents, yaml.RoundTripLoader)
            else:
                contents = yaml.safe_load(contents)
        elif sfile_type == 'json':
            contents = json.loads(contents)

        return contents

    @staticmethod
    def filter_versions(stdout):
        ''' filter the oc version output '''

        version_dict = {}
        version_search = ['oc', 'openshift', 'kubernetes']

        for line in stdout.strip().split('\n'):
            for term in version_search:
                if not line:
                    continue
                if line.startswith(term):
                    version_dict[term] = line.split()[-1]

        # horrible hack to get openshift version in Openshift 3.2
        #  By default "oc version in 3.2 does not return an "openshift" version
        if "openshift" not in version_dict:
            version_dict["openshift"] = version_dict["oc"]

        return version_dict

    @staticmethod
    def add_custom_versions(versions):
        ''' create custom versions strings '''

        versions_dict = {}

        for tech, version in versions.items():
            # clean up "-" from version
            if "-" in version:
                version = version.split("-")[0]

            if version.startswith('v'):
                versions_dict[tech + '_numeric'] = version[1:].split('+')[0]
                # "v3.3.0.33" is what we have, we want "3.3"
                versions_dict[tech + '_short'] = version[1:4]

        return versions_dict

    @staticmethod
    def openshift_installed():
        ''' check if openshift is installed '''
        import yum

        yum_base = yum.YumBase()
        if yum_base.rpmdb.searchNevra(name='atomic-openshift'):
            return True

        return False

    # Disabling too-many-branches.  This is a yaml dictionary comparison function
    # pylint: disable=too-many-branches,too-many-return-statements,too-many-statements
    @staticmethod
    def check_def_equal(user_def, result_def, skip_keys=None, debug=False):
        ''' Given a user defined definition, compare it with the results given back by our query.  '''

        # Currently these values are autogenerated and we do not need to check them
        skip = ['metadata', 'status']
        if skip_keys:
            skip.extend(skip_keys)

        for key, value in result_def.items():
            if key in skip:
                continue

            # Both are lists
            if isinstance(value, list):
                if key not in user_def:
                    if debug:
                        print('User data does not have key [%s]' % key)
                        print('User data: %s' % user_def)
                    return False

                if not isinstance(user_def[key], list):
                    if debug:
                        print('user_def[key] is not a list key=[%s] user_def[key]=%s' % (key, user_def[key]))
                    return False

                if len(user_def[key]) != len(value):
                    if debug:
                        print("List lengths are not equal.")
                        print("key=[%s]: user_def[%s] != value[%s]" % (key, len(user_def[key]), len(value)))
                        print("user_def: %s" % user_def[key])
                        print("value: %s" % value)
                    return False

                for values in zip(user_def[key], value):
                    if isinstance(values[0], dict) and isinstance(values[1], dict):
                        if debug:
                            print('sending list - list')
                            print(type(values[0]))
                            print(type(values[1]))
                        result = Utils.check_def_equal(values[0], values[1], skip_keys=skip_keys, debug=debug)
                        if not result:
                            print('list compare returned false')
                            return False

                    elif value != user_def[key]:
                        if debug:
                            print('value should be identical')
                            print(value)
                            print(user_def[key])
                        return False

            # recurse on a dictionary
            elif isinstance(value, dict):
                if key not in user_def:
                    if debug:
                        print("user_def does not have key [%s]" % key)
                    return False
                if not isinstance(user_def[key], dict):
                    if debug:
                        print("dict returned false: not instance of dict")
                    return False

                # before passing ensure keys match
                api_values = set(value.keys()) - set(skip)
                user_values = set(user_def[key].keys()) - set(skip)
                if api_values != user_values:
                    if debug:
                        print("keys are not equal in dict")
                        print(api_values)
                        print(user_values)
                    return False

                result = Utils.check_def_equal(user_def[key], value, skip_keys=skip_keys, debug=debug)
                if not result:
                    if debug:
                        print("dict returned false")
                        print(result)
                    return False

            # Verify each key, value pair is the same
            else:
                if key not in user_def or value != user_def[key]:
                    if debug:
                        print("value not equal; user_def does not have key")
                        print(key)
                        print(value)
                        if key in user_def:
                            print(user_def[key])
                    return False

        if debug:
            print('returning true')
        return True


class OpenShiftCLIConfig(object):
    '''Generic Config'''
    def __init__(self, rname, namespace, kubeconfig, options):
        self.kubeconfig = kubeconfig
        self.name = rname
        self.namespace = namespace
        self._options = options

    @property
    def config_options(self):
        ''' return config options '''
        return self._options

    def to_option_list(self):
        '''return all options as a string'''
        return self.stringify()

    def stringify(self):
        ''' return the options hash as cli params in a string '''
        rval = []
        for key, data in self.config_options.items():
            if data['include'] \
               and (data['value'] or isinstance(data['value'], int)):
                rval.append('--%s=%s' % (key.replace('_', '-'), data['value']))

        return rval


# -*- -*- -*- End included fragment: lib/base.py -*- -*- -*-

# -*- -*- -*- Begin included fragment: class/oc_sdnvalidator.py -*- -*- -*-

# pylint: disable=too-many-instance-attributes
class OCSDNValidator(OpenShiftCLI):
    ''' Class to wrap the oc command line tools '''

    def __init__(self, kubeconfig):
        ''' Constructor for OCSDNValidator '''
        # namespace has no meaning for SDN validation, hardcode to 'default'
        super(OCSDNValidator, self).__init__('default', kubeconfig)

    def get(self, kind, invalid_filter):
        ''' return SDN information '''

        rval = self._get(kind)
        if rval['returncode'] != 0:
            return False, rval, []

        return True, rval, filter(invalid_filter, rval['results'][0]['items'])

    # pylint: disable=too-many-return-statements
    @staticmethod
    def run_ansible(params):
        ''' run the idempotent ansible code

            params comes from the ansible portion of this module
        '''

        sdnvalidator = OCSDNValidator(params['kubeconfig'])
        all_invalid = {}
        failed = False

        checks = (
            (
                'hostsubnet',
                lambda x: x['metadata']['name'] != x['host'],
                u'hostsubnets where metadata.name != host',
            ),
            (
                'netnamespace',
                lambda x: x['metadata']['name'] != x['netname'],
                u'netnamespaces where metadata.name != netname',
            ),
        )

        for resource, invalid_filter, invalid_msg in checks:
            success, rval, invalid = sdnvalidator.get(resource, invalid_filter)
            if not success:
                return {'failed': True, 'msg': 'Failed to GET {}.'.format(resource), 'state': 'list', 'results': rval}
            if invalid:
                failed = True
                all_invalid[invalid_msg] = invalid

        if failed:
            return {'failed': True, 'msg': 'All SDN objects are not valid.', 'state': 'list', 'results': all_invalid}

        return {'msg': 'All SDN objects are valid.'}

# -*- -*- -*- End included fragment: class/oc_sdnvalidator.py -*- -*- -*-

# -*- -*- -*- Begin included fragment: ansible/oc_sdnvalidator.py -*- -*- -*-

def main():
    '''
    ansible oc module for validating OpenShift SDN objects
    '''

    module = AnsibleModule(
        argument_spec=dict(
            kubeconfig=dict(default='/etc/origin/master/admin.kubeconfig', type='str'),
        ),
        supports_check_mode=False,
    )


    rval = OCSDNValidator.run_ansible(module.params)
    if 'failed' in rval:
        module.fail_json(**rval)

    module.exit_json(**rval)

if __name__ == '__main__':
    main()

# -*- -*- -*- End included fragment: ansible/oc_sdnvalidator.py -*- -*- -*-
