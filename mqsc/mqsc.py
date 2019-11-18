#!/usr/bin/python


ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['alpha'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: mqsc

short_description: Simple module to manage an IBM MQ9 installation.

version_added: "2.9"

description:
    - "This module was made in order to manage an IBM MQ 9 installation.
    it can create Channels, Queues and QManagers."

options:
    name:
        description:
            - This is the message to send to the test module
        required: true
    new:
        description:
            - Control to demo if the result of this module is changed or not
        required: false

author:
    - Charl-Alexandre Le Brun (@Ramoreik)
'''

EXAMPLES = '''
TODO
'''

RETURN = '''
TODO
'''
import os
import re
import time
import shlex
import traceback
import subprocess
from ansible.module_utils.basic import AnsibleModule

module = None

MODULE_TEMP_FOLDER = os.path.join(os.path.sep ,'tmp', 'mqsc_ansible_temp')
IMPORTANT_BINARIES_LOCATION = {
    'RUNMQSC' : '/usr/bin/runmqsc',
    'CRTMQM' : '/usr/bin/crtmqm',
    'STRMQM' : '/usr/bin/strmqm',
    'DSPMQ' : '/usr/bin/dspmq',
    'DSPMQVER' : '/usr/bin/dspmqver',
    'ENDMQM' : '/usr/bin/endmqm',
    'DLTMQM' : '/usr/bin/dltmqm'
}

# ================================================================================
# DEVNOTE:
# Classes that manage the different MQSC concepts, QMGR, QUEUES and CHANNELS.

class QMGR():
    DSPMQ_REGEX = r'QMNAME\(([A-Za-z0-9]*)\) *STATUS\(([A-Za-z]*)\)'
    DISPLAY_QUEUE_REGEX = r' *QUEUE\(([A-Z\_\.]*)\) *[\n]?TYPE\(([A-Z]*)\)'
    QUEUE_ATTRIBUTES_REGEX = r'   ([A-Z]*)\(([A-Z_\-\.[0-9\\ ]*)\)'
    #TODO: Add channels
    #TODO: Add altering queues and channels (this will give true idempotence)
    #TODO: Validate the power status of a qmgr and only start it when needed
    #TODO: Add a temporary folder for debugging purposes
    #TODO: Add multiple ways of interacting with mqsc

    def __init__(self, name, queues=[], channels=[]):
        self.name = name
        self.commands_pending = []
        self.existing_queues = []
        self.queues = queues
        self.channels = channels
        self.mqsc_cmds = []
        self.fetch_current_state()

    def fetch_current_state(self):
        self.retrieve_existing_queues()
        self.parse_existing_queues()
        open(os.path.join(MODULE_TEMP_FOLDER, 'fetch_current_state.out'), 'w').write(str(self.existing_queues))

    def execute_mqsc_script(self):
        print("execute mqsc script")

    def generate_mqsc_script(self):
        print("execute mqsc script")

    def run_isolated_mqsc_cmd(self, out, cmd):
        cmd = "echo '%s' | %s %s" % (
            cmd,
            IMPORTANT_BINARIES_LOCATION["RUNMQSC"],
            self.name
        )
        output = execute_raw_command(cmd)
        stdout = "CMD: %s \n" % cmd
        stdout += retrieve_stdout(output)
        open(out, 'w').write(stdout)

    def run_mqsc_cmd_stdout(self, cmd):
        cmd = "echo '%s' | %s %s" % (
            cmd,
            IMPORTANT_BINARIES_LOCATION['RUNMQSC'],
            self.name
        )
        output = execute_raw_command(cmd)
        return retrieve_stdout(output)

    def parse_dspmq(self):
        cmd = IMPORTANT_BINARIES_LOCATION['DSPMQ']
        result = execute_command(cmd)
        matches = []
        for line in result.stdout:
            match = re.match(self.DSPMQ_REGEX, line)
            if match:
                module.log("MATCH : %s" % match)
                matches.append(list(match.groups()))
        module.log("groups : %s" % matches)
        return matches

    def exists(self):
        parsed_dspmq = self.parse_dspmq()
        module.log("DSPMQ RESULTS : %s" % str(parsed_dspmq))
        if parsed_dspmq:
            for entry in parsed_dspmq:
                module.log("ENTRY : %s" % str(entry))
                if self.name in entry:
                    return True

    def create(self):
        cmd = shlex.split("%s %s" % (IMPORTANT_BINARIES_LOCATION['CRTMQM'], self.name))
        output = execute_command(cmd)
        print_command_output(output)

    def start(self):
        cmd = shlex.split("%s %s" % (IMPORTANT_BINARIES_LOCATION['STRMQM'], self.name))
        output = execute_command(cmd)
        print_command_output(output)

    def stop(self):
        cmd = shlex.split("%s -w %s" % (IMPORTANT_BINARIES_LOCATION['ENDMQM'], self.name))
        output = execute_command(cmd)
        print_command_output(output)

    def delete(self):
        cmd = shlex.split("%s %s" % (IMPORTANT_BINARIES_LOCATION['DLTMQM'], self.name))
        output = execute_command(cmd)
        print_command_output(output)

    def handle_queues(self):
        for queue in self.queues:
            existing_queue = self.queue_exists(queue)
            if queue["state"] == "present":
                if existing_queue:
                    self.alter_queue(queue, existing_queue)
                else:
                    self.create_queue(queue)

            elif queue["state"] == "absent":
                if existing_queue is not None:
                    self.delete_queue(queue)

    def queue_exists(self, queue):
        seeked_queue = None
        for existing_queue in self.existing_queues:
            if existing_queue['name'] == queue['name']\
                and existing_queue['type'] == queue['type']:
                seeked_queue = existing_queue
        return seeked_queue

    def delete_queue(self, queue_config):
        queue = Queue(queue_config["name"], queue_config["type"], queue_config["opts"])
        output_file = os.path.join(MODULE_TEMP_FOLDER, '%s_delete_queue.out' % queue_config["name"])
        self.run_isolated_mqsc_cmd(output_file, queue.generate_delete_cmd())

    def alter_queue(self, wanted_queue, existing_queue):
        queue = Queue(existing_queue['name'], existing_queue['type'], existing_queue['opts'])
        output_file = os.path.join(MODULE_TEMP_FOLDER, '%s_alter_queue.out' % existing_queue['name'])
        cmd = queue.generate_alter_cmd(wanted_queue)
        if cmd:
            self.run_isolated_mqsc_cmd(output_file, cmd)

    def create_queue(self, queue_config):
        queue = Queue(queue_config["name"], queue_config["type"], queue_config["opts"])
        output_file = os.path.join(MODULE_TEMP_FOLDER, '%s_create_queue.out' % queue_config["name"])
        self.run_isolated_mqsc_cmd(output_file, queue.generate_define_cmd())

    def retrieve_existing_queues(self):
        #TODO: Refactor this function it ressembles parse dspmq too much
        print("do regex to parse display output")
        cmd = "DISPLAY QUEUE(*)"
        queues = self.run_mqsc_cmd_stdout(cmd)
        matches = []
        lines = []
        for line in queues.split('\n'):
            match = re.match(self.DISPLAY_QUEUE_REGEX, line)
            lines.append(line)
            if match:
                matches.append(list(match.groups()))
        for match in matches:
            queue = {
                "name" : match[0],
                "type" : match[1]
            }
            self.existing_queues.append(queue)

    def parse_existing_queues(self):
        #TODO: Refactor this function it ressembles parse dspmq too much
        #TODO: find a better solution for hotfix on line 223
        queues = []
        for queue in self.existing_queues:
            cmd = "DISPLAY QUEUE(%s)" % queue['name']
            stdout = self.run_mqsc_cmd_stdout(cmd)
            stdout = stdout.replace('\n','')
            matches = re.findall(self.QUEUE_ATTRIBUTES_REGEX, stdout)
            defined_queue = {
                "name": queue['name'],
                "type": queue['type'],
                "opts": {}
            }
            for match in matches:
                defined_queue["opts"][match[0]] = match[1]
            queues.append(defined_queue)
        self.existing_queues = queues


    def display_queues(self):
        output_file = os.path.join(MODULE_TEMP_FOLDER, "display_queues.out")
        self.run_isolated_mqsc_cmd(output_file, "DISPLAY QUEUE(*)")

    def handle_channels(self):
        for channel in self.channels:
            if channel['state'] == "present":
                self.create_channel(channel)

            elif channel['state'] == 'absent':
                self.delete_channel(channel)

    def delete_channel(self, channel_config):
        channel = Channel(channel_config['name'], channel_config['type'], channel_config['opts'])
        output_file = os.path.join(MODULE_TEMP_FOLDER, '%s_delete_channel.out' % channel_config['name'] )
        self.run_isolated_mqsc_cmd(output_file, channel.generate_delete_cmd())

    def alter_channel(self, channel_config):
        print('function to alter channel')

    def create_channel(self, channel_config):
        channel = Channel(channel_config['name'], channel_config['type'], channel_config['opts'])
        output_file = os.path.join(MODULE_TEMP_FOLDER, '%s_create_channel.out' % channel_config['name'])
        self.run_isolated_mqsc_cmd(output_file, channel.generate_define_cmd())

    def display_channels(self):
        output_file = os.path.join(MODULE_TEMP_FOLDER, "display_channels.out")
        self.run_isolated_mqsc_cmd(output_file, "DISPLAY CHANNEL(*)")


class Queue():
    QTYPES = [
        'QLOCAL',
        'QREMOTE',
        'QALIAS',
        'QMODEL'
    ]

    VALID_ATTRIBUTES = {
        "QLOCAL" : [
            'ACCTQ', 'BOQNAME', 'BOTHRESH',
            'CLCHNAME', 'CLUSNL', 'CLUSTER',
            'CLWLPRTY', 'CLWLRANK', 'CLWLUSEQ',
            'CUSTOM', 'DEFBIND', 'DEFPRESP',
            'DEFPRTY', 'DEFPSIST', 'DEFREADA',
            'DEFSOPT', 'DESCR', 'DISTL',
            'FORCE', 'GET', 'IMGRCOVQ',
            'INDXTYPE', 'INITQ', 'LIKE',
            'MAXDEPTH', 'MAXMSGL', 'MONQ',
            'MSGDLVSQ', 'NOREPLACE', 'NPMCLASS',
            'PROCESS', 'PROPCTL', 'PUT',
            'QDEPTHHI', 'QDEPTHLO', 'QDPHIEV',
            'QDPLOEV', 'QDPMAXEV', 'QSVCIEV',
            'QSVINT', 'REPLACE', 'RETINTVL',
            'SCOPE', 'SHARE', 'NOSHARE',
            'STATQ', 'TRIGDATA', 'TRIGDPTH',
            'TRIGGER', 'NOTRIGGER', 'TRIGMPRI',
            'TRIGTYPE', 'USAGE'
        ],
        "QMODEL" : [
            'ACCTQ', 'BOQNAME', 'BOTHRESH',
            'CUSTOM', 'DEFPRESP', 'DEFPRTY',
            'DEFPSIST', 'DEFREADA', 'DEFSOPT',
            'DEFTYPE', 'DESCR', 'DISTL',
            'GET', 'INDXTYPE', 'INITQ',
            'LIKE', 'MAXDEPTH', 'MAXMSGL',
            'MONQ', 'MSGDLVSQ', 'NOREPLACE',
            'NPMCLASS', 'PROCESS', 'PROPCTL',
            'PUT', 'QDEPTHHI', 'QDEPTHLO',
            'QDPHIEV', 'QDPLOEV', 'QDPMAXEV',
            'QSVCIEV', 'QSVCINT', 'REPLACE',
            'RETINTVL', 'SHARE', 'NOSHARE',
            'STATQ', 'TRIGDATA', 'TRIGDTPH',
            'TRIGGER', 'NOTRIGGER', 'TRIGMPRI',
            'TRIGTYPE', 'USAGE'
        ],
        "QALIAS" : [
            'CLUSNL', 'CLUSTER', 'CLWLPRTY',
            'CLWLRANK', 'CUSTOM', 'DEFBIND',
            'DEFPRESP', 'DEFPRTY', 'DEFPSIST',
            'DEFREADA', 'DESCR', 'FORCE',
            'GET', 'LIKE', 'NOREPLACE',
            'PROPCTL', 'PUT', 'REPLACE',
            'SCOPE', 'TARGET', 'TARGQ',
            'TARGTYPE'
        ],
        "QREMOTE" : [
            'CLUSNL', 'CLUSTER', 'CLWLPRTY',
            'CLWLRANK', 'CUSTOM', 'DEFBIND',
            'DEFPRESP', 'DEFPRTY', 'DEFPSIST',
            'DESCR', 'FORCE', 'LIKE',
            'NOREPLACE', 'PUT', 'REPLACE',
            'RNAME', 'RQMNAME', 'SCOPE',
            'XMITQ'
        ]
    }

    def __init__(self, name, qtype, options):
        if qtype in self.QTYPES:
            self.type = qtype
        else:
            raise Exception("Unknown Queue type")
        self.name = name
        self.options = options
        self.args = []

    def generate_define_cmd(self):
        cmd = "DEFINE %s(%s) " % (self.type, self.name)
        if self.options:
            self.handle_options()
            if len(self.args) > 0:
                cmd += ' '.join(self.args)
        return cmd

    def generate_alter_cmd(self, wanted_queue):
        attributes_to_alter = self.handle_queue_delta(wanted_queue['opts'])
        if len(attributes_to_alter) > 0:
            cmd = "ALTER %s(%s) " % (wanted_queue['type'], wanted_queue['name'])
            cmd += ' '.join(attributes_to_alter)
            return cmd

    def handle_queue_delta(self, wanted_options):
        attributes_to_alter = []
        for opt in wanted_options:
            if isinstance(wanted_options[opt], str):
                wanted_options[opt] = wanted_options[opt].upper()
            if wanted_options[opt]:
                if self.options[opt] != str(wanted_options[opt]):
                    attributes_to_alter.append("%s(%s)" % (opt, wanted_options[opt]))
        return attributes_to_alter

    def generate_delete_cmd(self):
        return "DELETE %s(%s)" % (self.type, self.name)

    def handle_option(self, attribute, value):
        if value:
            if isinstance(value, str):
                value = value.replace(" ", "")
            self.args.append("%s(%s)" % (attribute, value))

    def handle_options(self):
        if self.VALID_ATTRIBUTES.get(self.type, False):
            for option in self.options:
                if option in self.VALID_ATTRIBUTES[self.type]:
                    self.handle_option(option, self.options[option])


class Channel():
    #TODO: ADD SVRCONN, CLUSSDR, CLUSRCVR, AMQP
    CHLTYPE = [
        'SDR', 'SVR', 'RCVR',
        'RQSTR', 'CLNTCONN', 'SVRCONN',
        'CLUSSDR', 'CLUSRCVR', 'AMQP'
    ]

    VALID_ATTRIBUTES = {
        'SDR': [
            'BATCHHB', 'BATCHINT', 'BATCHLIM',
            'BATCHSZ', 'CERTLABL', 'CHLTYPE',
            'CMDSCOPE', 'COMPHDR', 'COMPMSG',
            'CONNAME', 'CONVERT', 'DEFCDISP',
            'DESCR', 'DISCINT', 'HBINT',
            'KAINT', 'LIKE', 'LOCLADDR',
            'LONGRTY', 'LONGTMR', 'MAXMSGL',
            'MCANAME', 'MCATYPE', 'MODENAME',
            'MONCHL', 'MSGDATA', 'MSGEXIT',
            'NPMSPEED', 'PASSWORD', 'PROPCTL',
            'QSDISP', 'RCVDATA', 'RCVEXIT',
            'REPLACE', 'SCYDATA', 'SCYEXIT',
            'SENDDATA', 'SENDEXIT', 'SEQWRAP',
            'SHORTRTY', 'SHORTTMR', 'SSLCIPH',
            'SSLPEER', 'STATCHL', 'TPNAME',
            'TPROOT', 'USECLTID', 'USEDLQ',
            'USERID', 'XMITQ'
        ],
        'SVR' : [
            'BATCHHB', 'BATCHINT', 'BATCHLIM',
            'BATCHSZ', 'CERTLABL', 'CHLTYPE',
            'CMDSCOPE', 'COMPHDR', 'COMPMSG',
            'CONNAME', 'CONVERT', 'DEFCDISP',
            'DESCR', 'DISCINT', 'HBINT',
            'KAINT', 'LIKE', 'LOCLADDR',
            'LONGRTR', 'LONGTMR', 'MAXMSGL',
            'MCANAME', 'MCATYPE', 'MODENAME',
            'MONCHL', 'MSGDATA', 'MSGEXIT',
            'NPMSPEED', 'PASSWORD', 'PROPCTL',
            'PORT', 'QSDISP', 'RCVDATA',
            'RCVEXIT', 'REPLACE', 'SCYDATA',
            'NOREPLACE', 'SCYEXIT', 'SENDDATA',
            'SENDEXIT', 'SEQWRAP', 'SHORTRTY',
            'SHORTTMR', 'SSLCIPH', 'SSLPEER',
            'STATCHL', 'TPNAME', 'TPROOT',
            'TRPTYPE', 'USECLTID', 'USEDLQ',
            'USERID', 'XMITQ'
        ],
        'RCVR' : [
            'BATCHSZ', 'CERTLABL', 'CHLTYPE',
            'CMDSCOPE', 'COMPHDR', 'COMPMSG',
            'CONVERT', 'DESCR', 'HBINT',
            'KAINT', 'LIKE', 'MAXMSGL',
            'MCAUSER', 'MONCHL', 'MRDATA',
            'MREXIT', 'MRRTY', 'MRTMR',
            'MSGDATA', 'MSGEXIT', 'NPMSPEED',
            'PORT', 'PUTAUT', 'QSDISP',
            'RCVDATA', 'RCVEXIT', 'REPLACE',
            'SCYDATA', 'SCYEXIT', 'SENDDATA',
            'SENDEXIT', 'SEQWRAP', 'SSLCAUTH',
            'SSLCIPH', 'SSLPEER', 'STATCHL',
            'TPROOT', 'TRPTYPE', 'USECLTID',
            'USEDLQ'
        ],
        'RQSTR' : [
            'BATCHSZ', 'CERTLABL', 'CHLTYPE',
            'CMDSCOPE', 'COMPHDR', 'COMPMSG',
            'CONNAME', 'DESCR', 'DEFCDISP',
            'HBINT', 'KAINT', 'LIKE',
            'LOCLADDR', 'MAXMSGL', 'MCANAME',
            'MCATYPE', 'MCAUSER', 'MODENAE',
            'MONCHL', 'MRDATA', 'MREXIT',
            'MRRTY', 'MRTMR', 'MSGDATA',
            'MSGEXIT', 'NPMSPEED', 'PASSWORD',
            'PORT', 'PUTAUT', 'QSDISP',
            'RCVDATA', 'RCVEXIT', 'REPLACE',
            'SCYDATA', 'SCYEXIT', 'SENDDATA',
            'SENDEXIT', 'SEQWRAP', 'SSLCAUTH',
            'SSLCIPH', 'SSLPEER', 'TPNAME',
            'TPROOT', 'TRPTYPE', 'USECLTID',
            'USEDLQ', 'USERID'
        ],
        'CLNTCONN' : [
            'AFFINITY', 'CERTLABL', 'CHLTYPE',
            'CLNTWGHT', 'CMDSCOPE', 'COMPHDR',
            'COMPMSG', 'CONNAME', 'DEFRECON',
            'DESCR', 'HBINT', 'KAINT', 'LIKE',
            'LOCLADDR', 'MAXMSGL', 'MODENAME',
            'PASSWORD', 'QMNAME', 'QSDISP',
            'RCVDATA', 'RCVEXIT', 'REPLACE',
            'SCYDATA', 'SCYEXIT', 'SENDDATA',
            'SENDEXIT', 'SHARECNV', 'SSLCIPH',
            'SSLPEER', 'TPNAME', 'USECLTID',
            'USERID'
        ]
    }

    REQUIRED_ATTRIBUTES = {
        'SVR' : [
            'XMITQ'
        ],
        'SDR' : [
            'CONNAME',
            'XMITQ'
        ],
        'RQSTR' : [
            'CONNAME'
        ]
    }
    def __init__(self, name, chltype, options):
        if chltype in self.CHLTYPE:
            self.type = chltype
        else:
            raise Exception("Unknown Channel type")
        self.name = name
        self.options = options
        self.args = []

    def validate_required_options(self):
        if self.REQUIRED_ATTRIBUTES.get(self.type, False):
            for required_attribute in self.REQUIRED_ATTRIBUTES[self.type]:
                if not self.options[required_attribute]:
                    raise Exception("Missing required option : %s for %s channel." \
                        % (required_attribute, self.type))

    def generate_define_cmd(self):
        self.validate_required_options()
        cmd = "DEFINE CHANNEL(%s) CHLTYPE(%s) " % (self.name, self.type)
        if self.options:
            self.handle_options()
            if len(self.args) > 0:
                cmd += ' '.join(self.args)
        return cmd

    def genrate_alter_cmd(self):
        print("Function to generate the alter command for this channel")

    def generate_delete_cmd(self):
        return "DELETE CHANNEL(%s)" % self.name

    def handle_option(self, attribute, value):
        if value:
            if isinstance(value, str):
                value = value.replace(" ", "")
            self.args.append("%s(%s)" % (attribute, value))

    def handle_options(self):
        if self.VALID_ATTRIBUTES.get(self.type, False):
            for option in self.options:
                if option in self.VALID_ATTRIBUTES[self.type]:
                    self.handle_option(option, self.options[option])


# ================================================================================
# DEVNOTE:
# possible refactoring into a class with static methods that will only execute commands and
# manage the interactions with the underlaying system

def create_temp_folder():
    if not os.path.exists(MODULE_TEMP_FOLDER):
        os.mkdir(MODULE_TEMP_FOLDER)

def print_command_output(pipe):
    stdout = ""
    for line in pipe.stdout:
        stdout += line
    module.log(stdout)

def retrieve_stdout(cmd_result):
    stdout = ""
    for line in cmd_result.stdout:
        stdout += line
    return stdout

def execute_command(cmd):
        output = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        output.wait()
        return output

def execute_raw_command(cmd):
        output = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
        output.wait()
        return output

# ================================================================================
# DEVNOTE:
# This portions contains the functions pertaining to the presence of the necessary binaries on the FS
# It will search the PATH, conventional locations and then fail if the binaries are not found.
# I plan to add arguments that could be passed to the module to specify where to find these binaries (normally /opt/mqm/bin)

def validate_binaries():
    for binary in IMPORTANT_BINARIES_LOCATION:
        binary_location = IMPORTANT_BINARIES_LOCATION[binary]
        if not os.path.exists(binary_location):
            module.warn("Missing mq binary : %s, the module may fail"\
                % binary_location)


def run_module():
    # QUEUE MQSC COMMANDS :  https://www.ibm.com/support/knowledgecenter/SSFKSJ_9.1.0/com.ibm.mq.ref.adm.doc/q085690_.htm
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        qmgr=dict(required=True, type='dict', options=dict(
            name=dict(required=True, type='str'),
            state=dict(type='str', default='present',choices=['present', 'absent']),
            channels=dict(type='list', elements='dict', options=dict(
              name=dict(required=True, type='str'),
              type=dict(required=True, type='str'),
              state=dict(type='str', default='present', choices=['present', 'absent']),
              opts=dict(type='dict', options=dict(
                  AFFINITY=dict(type='str', choices=['PREFERRED', 'NONE']),
                  BATCHHB=dict(type='int'),
                  BATCHINT=dict(type='int'),
                  BATCHLIM=dict(type='int'),
                  BATCHSZ=dict(type='int'),
                  CERTLABL=dict(type='str'),
                  CLNTWGHT=dict(type='int'),
                  CLUSNL=dict(type='str'),
                  CLUSTER=dict(type='str'),
                  CLWLPRTY=dict(type='int'),
                  CLWLRANK=dict(type='int'),
                  CLWLWGHT=dict(type='int'),
                  CMDSCOPE=dict(type='str'),
                  COMPHDR=dict(type='str', choices=['NONE', 'SYSTEM']),
                  COMPMSG=dict(type='str', choices=['NONE', 'RLE', 'ZLIBFAST', 'ZLIBHIGH', 'ANY']),
                  CONNAME=dict(type='str'),
                  CONVERT=dict(type='str', choices=['YES', 'NO']),
                  DEFCDISP=dict(type='str', choices=['PRIVATE', 'FIXSHARED', 'SHARED']),
                  DEFRECON=dict(type='str', choices=['NO', 'YES', 'QMGR', 'DISABLED']),
                  DESCR=dict(type='str'),
                  DISCINT=dict(type='int'),
                  HBINT=dict(type='int'),
                  KAINT=dict(type='int'),
                  LIKE=dict(type='str'),
                  LOCLADDR=dict(type='str'),
                  LONGRTY=dict(type='int'),
                  LONGTMR=dict(type='int'),
                  MAXINST=dict(type='int'),
                  MAXINSTC=dict(type='int'),
                  MAXMSGL=dict(type='int'),
                  MCANAME=dict(type='str'),
                  MCATYPE=dict(type='str', choices=['PROCESS', 'THREAD']),
                  MCAUSER=dict(type='str'),
                  MODENAME=dict(type='str'),
                  MONCHL=dict(type='str', choices=['QMGR', 'OFF', 'LOW', 'MEDIUM', 'HIGH']),
                  MRDATA=dict(type='str'),
                  MREXIT=dict(type='str'),
                  MRRTY=dict(type='int'),
                  MRTRM=dict(type='int'),
                  MSGDATA=dict(type='str'),
                  MSGEXIT=dict(type='str'),
                  NETPRTY=dict(type='int'),
                  NPMSPEED=dict(type='str', choices=['FAST', 'NORMAL']),
                  PASSWORD=dict(type='str'),
                  PROPCTL=dict(type='str', choices=['COMPAT', 'NONE', 'ALL']),
                  PUTAUT=dict(type='str', choices=['DEF', 'CTX', 'ONLYMCA', 'ALTMCA']),
                  QMNAME=dict(type='str'),
                  QSGDISP=dict(type='str', choice=['COPY', 'GROUP', 'PRIVATE', 'QMGR']),
                  RCVDATA=dict(type='str'),
                  RCVEXIT=dict(type='str'),
                  REPLACE=dict(type='bool'),
                  NOREPLACE=dict(type='bool'),
                  SCYDATA=dict(type='str'),
                  SCYEXIT=dict(type='str'),
                  SENDDATA=dict(type='str'),
                  SENDEXIT=dict(type='str'),
                  SEQWRAP=dict(type='int'),
                  SHARECNV=dict(type='int'),
                  SHORTTRY=dict(typ='int'),
                  SHOTTMR=dict(type='int'),
                  SSLCAUTH=dict(type='str', choices=['REQUIRED', 'OPTIONAL']),
                  SSLCIPH=dict(type='str'),
                  SSLPEER=dict(type='str'),
                  STATCHL=dict(type='str', choices=['QMGR', 'OFF', 'LOW', 'MEDIUM', 'HIGH']),
                  TPNAME=dict(type='str'),
                  TPROOT=dict(type='str'),
                  TRPTYPE=dict(type='str', choices=['LU62', 'NETBIOS', 'SPX', 'TCP']),
                  USECLID=dict(type='bool'),
                    USEDLQ=dict(type='str', choices=['NO','YES']),
                    USERID=dict(type='str'),
                    XMITQ=dict(type='str')
              ))
            )),
            queues=dict(type='list', elements='dict', options=dict(
                name=dict(required=True, type='str'),
                type=dict(required=True, type='str', choices=["QLOCAL", "QMODEL", "QALIAS", "QREMOTE"]),
                state=dict(type='str', default='present', choices=['present', 'absent']),
                opts=dict(type='dict', options=dict(
                  DESCR=dict(type='str'),
                  ACCTQ=dict(type='str', choices=['ON', 'OFF', 'QMGR']),
                  BOQNAME=dict(type='str'),
                  BOTHRESH=dict(type='int'),
                  CLCHNAME=dict(type='str'),
                  CLUSNL=dict(type='list', elements='str'),
                  CLUSTER=dict(type='str'),
                  CLWLPRTY=dict(type='int'),
                  CLWLRANK=dict(type='int'),
                  CLWLUSEQ=dict(type='str', choices=['QMGR', 'ANY', 'LOCAL','*','']),
                  CUSTOM=dict(type='str'),
                  CAPEXPRY=dict(type='int'),
                  DEFBIND=dict(type='str', choice=['OPEN', 'NOTFIXED', 'GROUP']),
                  DEFPRESP=dict(type='str', choice=['SYNC', 'ASYNC']),
                  DEFPRTY=dict(type='int'),
                  DEFPSIST=dict(type='str', choices=['NO','YES']),
                  DEFREADA=dict(type='str', choices=['NO', 'YES', 'DISABLED']),
                  DEFSOPT=dict(type='str', choices=['EXCL', 'SHARED']),
                  DEFTYPE=dict(type='str', choices=['PERMDYN', 'TEMPDYN']),
                  DISTL=dict(type='str', choices=['YES', 'NO']),
                  FORCE=dict(type='bool'),
                  GET=dict(type='str', choices=['ENABLED', 'DISABLED']),
                  IMGRCOVQ=dict(type='str', choices=['YES', 'NO', 'QMGR']),
                  INITQ=dict(type='str'),
                  LIKE=dict(type='str'),
                  MAXDEPTH=dict(type='int'),
                  MAXMSGL=dict(type='int'),
                  MONQ=dict(type='str', choices=['QMGR', 'OFF', 'LOW', 'MEDIUM', 'HIGH']),
                  MSGDLVSQ=dict(type='str', choices=['PRIORITY', 'FIFO']),
                  NPMCLASS=dict(type='str', choices=['NORMAL', 'HIGH']),
                  PROCESS=dict(type='str'),
                  PROPCTL=dict(type='str', choices=['ALL', 'FORCE', 'COMPAT', 'NONE']),
                  PUT=dict(type='str', choices=['ENABLED', 'DISABLED']),
                  QDEPTHHI=dict(type='int'),
                  QDEPTHLO=dict(type='int'),
                  QDPHIEV=dict(type='str', choices=['ENABLED', 'DISABLED']),
                  QDPLOEV=dict(type='str', choices=['ENABLED', 'DISABLED']),
                  QDPMAXEV=dict(type='str', choices=['ENABLED', 'DISABLED']),
                  QSVCIEV=dict(type='str', choices=['HIGH', 'OK', 'NONE']),
                  QSVCINT=dict(type='int'),
                  REPLACE=dict(type='bool'),
                  NOREPLACE=dict(type='bool'),
                  RETINTVL=dict(type='int'),
                  RNAME=dict(type='str'),
                  RQMNAME=dict(type='str'),
                  SCOPE=dict(type='str', choices=['QMGR', 'CELL']),
                  SHARE=dict(type='bool'),
                  NOSHARE=dict(type='bool'),
                  STATQ=dict(type='str', choices=['QMGR', 'ON', 'OFF']),
                  TARGET=dict(type='str'),
                  TARGTYPE=dict(type='str'),
                  TRIGDATA=dict(type='str'),
                  TRIGDPTH=dict(type='int'),
                  TRIGGER=dict(type='bool'),
                  NOTRIGGER=dict(type='bool'),
                  TRIGMPRI=dict(type='int'),
                  TRIGTYPE=dict(type='str', choices=['FIRST', 'EVERY', 'DEPTH', 'NONE']),
                  USAGE=dict(type='str', choices=['NORMAL', 'XMITQ']),
                  XMITQ=dict(type='str')
                ))
            ))
        ))
    )

    global module

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    result = dict(
        changed=False,
        original_message='',
        message=''
    )

    create_temp_folder()
    qmgr_name = module.params['qmgr']['name']
    qmgr_state = module.params['qmgr']['state']
    qmgr_queues = module.params['qmgr']['queues']
    qmgr_channels = module.params['qmgr']['channels']
    qmgr = QMGR(qmgr_name, qmgr_queues, qmgr_channels)

    if qmgr_state == "present":
        qmgr_exists = qmgr.exists()
        if not qmgr_exists:
            qmgr.create()
            qmgr.start()
            qmgr.handle_queues()
            qmgr.display_queues()
            result['changed'] = True

        if qmgr_exists:
            if len(qmgr_queues) > 0:
                qmgr.start()
                qmgr.handle_queues()
                qmgr.display_queues()
                result['changed'] = True

            if len(qmgr_channels) > 0:
                qmgr.start()
                qmgr.handle_channels()
                qmgr.display_channels()
                result['changed'] = True
            module.exit_json(**result)

    if qmgr_state == "absent":
        if qmgr.exists():
            qmgr.stop()
            qmgr.delete()
            result['changed'] = True

    if module.check_mode:
        module.exit_json(**result)

    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()