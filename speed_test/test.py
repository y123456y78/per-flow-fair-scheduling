import logging
import time
from ptf import config
import ptf.testutils as testutils
from bfruntime_client_base_tests import BfRuntimeTest
import bfrt_grpc.client as gc
from tm_api_rpc.ttypes import *
from pal_rpc.ttypes import *
##### Required for Thrift #####
import pd_base_tests
from ptf.thriftutils import *
from res_pd_rpc.ttypes import *
from tm_api_rpc.ttypes import *
import numpy as np
##### ******************* #####

def get_res(res):
    mean = np.mean(res)
    dev = np.std(res)
    print("(Mean, Deviation):",(mean,dev))

logger = logging.getLogger('Test')
if not len(logger.handlers):
    logger.addHandler(logging.StreamHandler())

class PtfTest(BfRuntimeTest):
    class FixedAPIs(pd_base_tests.ThriftInterfaceDataPlane):
        def __init__(self, p4names):
            pd_base_tests.ThriftInterfaceDataPlane.__init__(self, p4names)
            
        def setUp(self):
            pd_base_tests.ThriftInterfaceDataPlane.setUp(self)
            
            self.dev = 0
            self.dev_tgt  = DevTarget_t(self.dev, -1)
            self.sess_hdl = self.conn_mgr.client_init()
            print("Opened Connection Mgr  Session {:#08x}".
                  format(self.sess_hdl))
        
        def runTest(self):
            pass
        
        def tearDown(self):
            self.conn_mgr.complete_operations(self.sess_hdl)
            self.conn_mgr.client_cleanup(self.sess_hdl)
            print("  Closed ConnMgr Session {}".format(self.sess_hdl))
            pd_base_tests.ThriftInterfaceDataPlane.tearDown(self)

    def setUp(self):
        client_id = 0
        p4_name = "per_flow_q"
      
        BfRuntimeTest.setUp(self, client_id, p4_name) 
    def runTest(self):

        p4_name = "per_flow_q"
        eg_port_h3 = 58 #h3
        eg_port_m1 = 164 #m1
        eg_port_h4 = 59 #h4
        dmac_h3 = '00:1b:21:bc:aa:d3' #h3
        dmac_m1 = 'ec:0d:9a:d9:d0:7a' #m1
        dmac_h4 = '00:1b:21:bc:aa:36' #h4
        #dmac_h12 = '90:e2:ba:c2:f6:76' #h12
        weight_base = 100
        forward_only = True
        
        # Get bfrt_info and set it as part of the test
        bfrt_info = self.interface.bfrt_info_get("per_flow_q")
        
        forward_table = bfrt_info.table_get("SwitchIngress.forward")
        forward_table.info.key_field_annotation_add("hdr.ethernet.dst_addr", "mac")

        qid_table = bfrt_info.table_get("SwitchIngress.qid")
        qid_table.info.key_field_annotation_add("ig_md.per_flow_hdr.fid", "ipv4")
        register_table = bfrt_info.table_get("SwitchIngress.reg")

        hash_table = bfrt_info.table_get("SwitchIngress.tab_hash")
        counter_table = bfrt_info.table_get("SwitchIngress.cnt")

        target = gc.Target(device_id=0, pipe_id=0xffff)
        
        '''
        port configuration start
        '''
        fixedObj = self.FixedAPIs([p4_name])
        fixedObj.setUp()
        print('h4 port rate: ',fixedObj.tm.tm_get_port_shaping_rate(0, eg_port_h4))
        if not forward_only:

        
            fixedObj.tm.tm_set_q_sched_priority(0,eg_port_m1,0,7)
            for i in range(8):
                print('m1 port Queue ',i,' priority: ',fixedObj.tm.tm_get_q_sched_priority(0,eg_port_m1,i))
            
            for i in range(7):
                fixedObj.tm.tm_set_q_dwrr_weight(0,eg_port_h4,i,weight_base)
            fixedObj.tm.tm_set_q_dwrr_weight(0,eg_port_h4,7,1023)
        
            fixedObj.tm.tm_set_q_sched_priority(0,eg_port_h4,7,7)
            for i in range(8):
                # print('h4 port Queue ',i,' priority: ',fixedObj.tm.tm_get_q_sched_priority(0,eg_port_h4,i))
                print('h4 port Queue ',i,' weight: ',fixedObj.tm.tm_get_q_dwrr_weight(0,eg_port_h4,i))
        ''' 
        port configuration end
        '''
        '''
        forward_table.entry_add(
            target,
            [forward_table.make_key([gc.KeyTuple("hdr.ethernet.dst_addr", dmac_h3)])],
            [forward_table.make_data(
                [gc.DataTuple('eg_port',eg_port_h3)],
                'SwitchIngress.set_eg_port')])
        '''

        write_record = []
        del_record = []
        for k in range(100):
            for i in range(100):
                #print(i)
                start = time.time()
                forward_table.entry_add(
                    target,
                    [forward_table.make_key([gc.KeyTuple("hdr.ethernet.dst_addr", i)])],
                    [forward_table.make_data(
                        [gc.DataTuple('eg_port',1)],
                        'SwitchIngress.set_eg_port')])
                end = time.time()
                total_time=end-start
                write_record.append(total_time)
            
            for i in range(100):
                start = time.time()
                forward_table.entry_del(
                    target,
                    [forward_table.make_key([gc.KeyTuple("hdr.ethernet.dst_addr", i)])])
                end = time.time()
                total_time=end-start
                del_record.append(total_time)
        print("Num of test",len(write_record))
        print("write")
        get_res(write_record)
        print("delete")
        get_res(del_record)
        register_table.entry_add(
            target,
            [register_table.make_key([gc.KeyTuple('$REGISTER_INDEX', 0)])],
            [register_table.make_data(
                [gc.DataTuple('SwitchIngress.reg.r_value',0)])])
            
