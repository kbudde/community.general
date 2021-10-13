#!/usr/bin/python

# Copyright: (c) 2021, Kris Budde <kris@budd.ee
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
---
module: mssql_script

short_description: Execute SQL scripts on a MSSQL database

version_added: "4.0.0"

description: Execute SQL scripts on a MSSQL database

options:
    name:
        description: Database to run script against
        required: false
        aliases: [ db ]
        default: 'master'
        type: str
    login_user:
        description: The username used to authenticate with
        type: str
    login_password:
        description: The password used to authenticate with
        type: str
    login_host:
        description: Host running the database
        type: str
        required: true
    login_port:
        description: Port of the MSSQL server. Requires login_host be defined as well.
        default: '1433'
        type: str
    script:
        description: The SQL script to be executed.
        required: true
        type: str
    output:
        description: Output format. 'dict' requires named columns to be returned otherwise an error is thrown.
        choices: [ "dict", "default" ]
        default: 'default'
        type: str
    params:
        description: |
            Parameters passed to the script as sql parameters. ('SELECT %(name)s"')
            example: '{"name": "John Doe"}'
        type: dict
notes:
   - Requires the pymssql Python package on the remote host. For Ubuntu, this
     is as easy as pip install pymssql (See M(ansible.builtin.pip).)
requirements:
   - python >= 2.7
   - pymssql

author:
    - Kris Budde (@kbudde)
'''

EXAMPLES = r'''
# Pass in a message
- name: Check DB connection
  community.general.mssql_script:
    login_user: "{{ mssql_login_user }}"
    login_password: "{{ mssql_login_password }}"
    login_host: "{{ mssql_host }}"
    login_port: "{{ mssql_port }}"
    db: master
    script: "SELECT 1"

- name: Query with parameter
  community.general.mssql_script:
    login_user: "{{ mssql_login_user }}"
    login_password: "{{ mssql_login_password }}"
    login_host: "{{ mssql_host }}"
    login_port: "{{ mssql_port }}"
    script: |
      SELECT name, state_desc FROM sys.databases WHERE name = %(dbname)s
    params:
      dbname: msdb
  register: result_params
- assert:
    that:
      - result_params.query_results[0][0][0][0] == 'msdb'
      - result_params.query_results[0][0][0][1] == 'ONLINE'

- name: two batches with default output
  community.general.mssql_script:
    login_user: "{{ mssql_login_user }}"
    login_password: "{{ mssql_login_password }}"
    login_host: "{{ mssql_host }}"
    login_port: "{{ mssql_port }}"
    script: |
      SELECT 'Batch 0 - Select 0'
      SELECT 'Batch 0 - Select 1'
      GO
      SELECT 'Batch 1 - Select 0'
  register: result_batches
- assert:
    that:
      - result_batches.query_results | length == 2 # two batch results
      - result_batches.query_results[0] | length == 2 # two selects in first batch
      - result_batches.query_results[0][0] | length == 1 # one row in first select
      - result_batches.query_results[0][0][0] | length == 1 # one column in first row
      - result_batches.query_results[0][0][0][0] == 'Batch 0 - Select 0' # each row contains a list of values.

- name: two batches with dict output
  community.general.mssql_script:
    login_user: "{{ mssql_login_user }}"
    login_password: "{{ mssql_login_password }}"
    login_host: "{{ mssql_host }}"
    login_port: "{{ mssql_port }}"
    output: dict
    script: |
      SELECT 'Batch 0 - Select 0' as b0s0
      SELECT 'Batch 0 - Select 1' as b0s1
      GO
      SELECT 'Batch 1 - Select 0' as b1s0
  register: result_batches_dict
- assert:
    that:
      - result_batches_dict.query_results | length == 2 # two batch results
      - result_batches_dict.query_results[0] | length == 2 # two selects in first batch
      - result_batches_dict.query_results[0][0] | length == 1 # one row in first select
      - result_batches_dict.query_results[0][0][0]['b0s0'] == 'Batch 0 - Select 0' # column 'b0s0' of first row
'''

RETURN = r'''
query_results:
    description: List of batches ( queries separated by 'GO' keyword)
    type: list
    returned: success
    sample: [[[["Batch 0 - Select 0"]], [["Batch 0 - Select 1"]]], [[["Batch 1 - Select 0"]]]]
    contains:
        queries:
            description: List of rows for each query
            type: list
            contains:
                rows:
                    description: list of rows returned by query
                    type: list
                    contains:
                        column_value:
                            description: list of column values
                            type: list
                            example: ["Batch 0 - Select 0"]
                            returned: success, if output is default
                        column_dict:
                            description: dict of columns and values
                            type: dict
                            example: {"col_name": "Batch 0 - Select 0"}
                            returned: success, if output is dict
queries:
    description: The output message that the test module generates.
    type: list
    returned: success
    sample: 'goodbye'
'''

from ansible.module_utils.basic import AnsibleModule, missing_required_lib
import traceback
PYMSSQL_IMP_ERR = None
try:
    import pymssql
except ImportError:
    PYMSSQL_IMP_ERR = traceback.format_exc()
    mssql_found = False
else:
    mssql_found = True


def db_exists(conn, cursor, db):
    cursor.execute("SELECT name FROM master.sys.databases WHERE name = %s", db)
    conn.commit()
    return bool(cursor.rowcount)


def run_module():
    module_args = dict(
        name=dict(required=False, aliases=['db'], default='master'),
        login_user=dict(default=''),
        login_password=dict(default='', no_log=True),
        login_host=dict(required=True),
        login_port=dict(default='1433'),
        script=dict(required=True),
        output=dict(default='default', choices=['dict', 'default']),
        params=dict(type='dict'),
    )

    result = dict(
        changed=False,
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )
    if not mssql_found:
        module.fail_json(msg=missing_required_lib(
            'pymssql'), exception=PYMSSQL_IMP_ERR)

    db = module.params['name']
    login_user = module.params['login_user']
    login_password = module.params['login_password']
    login_host = module.params['login_host']
    login_port = module.params['login_port']
    script = module.params['script']
    output = module.params['output']
    sql_params = module.params['params']

    login_querystring = login_host
    if login_port != "1433":
        login_querystring = "%s:%s" % (login_host, login_port)

    if login_user != "" and login_password == "":
        module.fail_json(
            msg="when supplying login_user arguments login_password must be provided")

    try:
        conn = pymssql.connect(
            user=login_user, password=login_password, host=login_querystring, database=db)
        cursor = conn.cursor()
    except Exception as e:
        if "Unknown database" in str(e):
            errno, errstr = e.args
            module.fail_json(msg="ERROR: %s %s" % (errno, errstr))
        else:
            module.fail_json(msg="unable to connect, check login_user and login_password are correct, or alternatively check your "
                                 "@sysconfdir@/freetds.conf / ${HOME}/.freetds.conf")

    conn.autocommit(True)

    if db and not db_exists(conn, cursor, db):
        module.exit_json(msg="Database %s does not exist" % db, **result)

    if output == 'dict':
        cursor = conn.cursor(as_dict=True)

    queries = script.split('\nGO\n')
    result['queries'] = queries
    # result['sql_params'] = sql_params # may contain sensitive data
    result['changed'] = True
    if module.check_mode:
        module.exit_json(**result)

    query_results = []
    try:
        for query in queries:
            cursor.execute(query, sql_params)
            qry_result = []
            rows = cursor.fetchall()
            while rows:
                qry_result.append(rows)
                rows = cursor.fetchall()
            query_results.append(qry_result)
    except Exception as e:
        return module.fail_json(msg="query failed", query=query, error=str(e), **result)

    result['query_results'] = query_results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
