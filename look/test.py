import logging
import time
from ptf import config
from tm_api_rpc.ttypes import *
from ptf.thriftutils import *
from bfruntime_client_base_tests import BfRuntimeTest
import ptf.testutils as testutils
import bfrt_grpc.client as gc
from pal_rpc.ttypes import *
##### Required for Thrift #####
import pd_base_tests
from ptf.thriftutils import *
from res_pd_rpc.ttypes import *
from tm_api_rpc.ttypes import *
##### ******************* #####

logger = logging.getLogger('Test')
if not len(logger.handlers):
    logger.addHandler(logging.StreamHandler())

swports = []
for device, port, ifname in config["interfaces"]:
    swports.append(port)
    swports.sort()

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
        eg_port = 59 #h4
        ack_port = 164 #m1
        flow_in_queue = [0,0,0,0,0,0,0,0]
        flow_q_dict = {}
        flow_pkt_dict = {}
        flow_cnt_index = {}
        queue_weight = [0,0,0,0,0,0,0,0]
        
        # Get bfrt_info and set it as part of the test
        bfrt_info = self.interface.bfrt_info_get("per_flow_q")
        
        qid_table = bfrt_info.table_get("SwitchIngress.qid")
        qid_table.info.key_field_annotation_add("ig_md.per_flow_hdr.fid", "ipv4")
        register = bfrt_info.table_get("SwitchIngress.reg")
        
        counter = bfrt_info.table_get("SwitchIngress.cnt")
       
        cnt_table = bfrt_info.table_get("SwitchIngress.tab_cnt")
        cnt_table.info.key_field_annotation_add("ig_md.per_flow_hdr.fid", "ipv4")
        target = gc.Target(device_id=0, pipe_id=0xffff)
        
        
        fixedObj = self.FixedAPIs([p4_name])
        fixedObj.setUp()
        '''
        Port configuration
        '''
        '''
        fixedObj.tm.tm_set_app_pool_size(0,4,10000)
        fixedObj.tm.tm_set_app_pool_size(0,5,20000)
        fixedObj.tm.tm_set_app_pool_size(0,6,20000)
        fixedObj.tm.tm_set_app_pool_size(0,7,10000)
        
        #for ack_port
        fixedObj.tm.tm_set_q_dwrr_weight(0,ack_port,0,1023)
        fixedObj.tm.tm_set_q_guaranteed_min_limit(0, ack_port, 0, 10000)
        fixedObj.tm.tm_set_q_app_pool_usage( 0, ack_port, 0, 4, 5000, 8, 50)
        print(fixedObj.tm.tm_get_q_app_pool_usage(0,ack_port,0))
        print(fixedObj.tm.tm_get_q_guaranteed_min_limit(0, ack_port, 0))
        #for eg_port
        for i in range(0,3):
            fixedObj.tm.tm_set_q_guaranteed_min_limit(0, eg_port, i, 10000)
            fixedObj.tm.tm_set_q_app_pool_usage( 0, eg_port, i, 5, 10000, 6, 2000)
        for i in range(3,7):
            fixedObj.tm.tm_set_q_guaranteed_min_limit(0, eg_port, i, 10000)
            fixedObj.tm.tm_set_q_app_pool_usage( 0, eg_port, i, 6, 6600, 5, 3000)

        fixedObj.tm.tm_set_q_guaranteed_min_limit(0, eg_port, 7, 10000)
        fixedObj.tm.tm_set_q_app_pool_usage( 0, eg_port, 7, 7, 10000, 8, 50)

        for i in range(0,8):
            print(fixedObj.tm.tm_get_q_app_pool_usage(0,eg_port,i))
            print(fixedObj.tm.tm_get_q_guaranteed_min_limit(0, eg_port, i))
        
        '''
        '''
        port configuration end
        '''

        num_pipes = int(testutils.test_param_get('num_pipes'))
        print('num_pipes: ',num_pipes)
        last_reg_value=0
        check_time = 300
        next_counter_id = 0
        while True :
                # Get from sw and check its value
            time.sleep(0.01)
            register.operations_execute(target, 'SyncRegisters')
            resp = register.entry_get(
                target,
                [register.make_key([gc.KeyTuple('$REGISTER_INDEX', 0)])],
                {"from_hw": False})
            data_dict = next(resp)[0].to_dict() 
            reg_value = data_dict["SwitchIngress.reg.r_value"][1]
            
            if (reg_value == last_reg_value) or (reg_value == 0) or (flow_q_dict.get(str(reg_value)) != None) :
                pass
            else:    
                for i in range(num_pipes):
                    print('data_dict ',i,': ',data_dict["SwitchIngress.reg.r_value"][i])
                print('new reg_value: ',reg_value)
                flow_num = 1000
                index = 1000
                if reg_value > 99999:
                    reg_value-=100000
                    for i in range(3,7):
                        if flow_num > flow_in_queue[i]:
                            flow_num = flow_in_queue[i]
                            index = i
                    if index<=6 and index>=3:
                        
                        qid_table.entry_add(
                        target,
                        [qid_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", reg_value)])],
                        [qid_table.make_data(
                        [gc.DataTuple('queue_id',index)],
                            'SwitchIngress.set_queue_id')])
                        
                        flow_in_queue[index]+=1
                        fixedObj.tm.tm_set_q_dwrr_weight(0,eg_port,index,100*flow_in_queue[index])
                        
                        cnt_table.entry_add(
                        target,
                        [cnt_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", reg_value)])],
                        [cnt_table.make_data(
                        [gc.DataTuple('counter_id',next_counter_id)],
                            'SwitchIngress.flow_count')])
                        
                        last_reg_value = reg_value+100000 #return to the read value
                        flow_q_dict[str(last_reg_value)] = index
                        flow_pkt_dict[str(last_reg_value)] = 0
                        flow_cnt_index[str(last_reg_value)] = next_counter_id
                        next_counter_id+=1
                    else:
                        print('index value error')
                else:    
                    for i in range(3):
                        if flow_num > flow_in_queue[i]:
                            flow_num = flow_in_queue[i]
                            index = i
                    if index<=2 and index>=0:
                        qid_table.entry_add(
                        target,
                        [qid_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", reg_value)])],
                        [qid_table.make_data(
                        [gc.DataTuple('queue_id',index)],
                            'SwitchIngress.set_queue_id')])
                        flow_in_queue[index]+=1
                        fixedObj.tm.tm_set_q_dwrr_weight(0,eg_port,index,100*flow_in_queue[index])
                        
                        cnt_table.entry_add(
                        target,
                        [cnt_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", reg_value)])],
                        [cnt_table.make_data(
                        [gc.DataTuple('counter_id',next_counter_id)],
                            'SwitchIngress.flow_count')])
                        
                        last_reg_value = reg_value #save the read value
                        flow_q_dict[str(last_reg_value)] = index
                        flow_pkt_dict[str(last_reg_value)] = 0
                        flow_cnt_index[str(last_reg_value)] = next_counter_id
                        next_counter_id+=1
                    else:
                        print('index value error')
            check_time-=1
            if check_time <= 0: 
                print('show info') 
                #queue info
                print('flow_in_queue: ',flow_in_queue)
                resp = qid_table.default_entry_get(target,
                    {"from_hw": False})
                for i in range(8):
                    queue_weight[i] = fixedObj.tm.tm_get_q_dwrr_weight(0,eg_port,i)
                print('queue_weight:',queue_weight)
                print(flow_q_dict)
                print(flow_pkt_dict)
                #flow counter
                for k in list(flow_pkt_dict.keys()):    
                    qid = flow_q_dict[k]
                    fid = int(k)
                    if fid > 99999:
                        fid-=100000
                    counter_id = flow_cnt_index[k]
                    cnt_resp = counter.entry_get(target,
                                       [counter.make_key([gc.KeyTuple('$COUNTER_INDEX', counter_id)])],
                                       {"from_hw": True},
                                       None)
                    cnt_data = next(cnt_resp)[0].to_dict()
                    flow_pkt_new = cnt_data["$COUNTER_SPEC_PKTS"]
                    flow_pkt_old = flow_pkt_dict[k]
                    
                    print(k,'new_recv_pkts: ',flow_pkt_new,'old_recv_pkts: ',flow_pkt_old)
                    if flow_pkt_new > flow_pkt_old:
                        flow_pkt_dict[k] = flow_pkt_new
                    else:
                        print('flow ',k,' is end, delete')
                        qid_table.entry_del(
                        target,
                        [qid_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])])
                         
                        cnt_table.entry_del(
                        target,
                        [cnt_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])])
                        
                        flow_in_queue[qid]-=1
                        fixedObj.tm.tm_set_q_dwrr_weight(0,eg_port,qid,100*flow_in_queue[qid])
                        if flow_in_queue[qid] == 0:
                            fixedObj.tm.tm_set_q_dwrr_weight(0,eg_port,qid,100)
                        del flow_q_dict[k]
                        del flow_pkt_dict[k]
                        del flow_cnt_index[k]
                check_time = 300


            

