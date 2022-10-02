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
        self.p4_name = "per_flow_q"
        self.eg_port = 59 #h4
        self.flow_in_queue = [[],[],[],[],[],[],[],[]]
        self.queue_interval = [[],[],[],[]]
        self.tcp_queue = range(0,2) # queue 0, 1
        self.udp_queue = range(2,6) # queue 2, 3, 4, 5
        self.weight_base = 100

        client_id = 0
        BfRuntimeTest.setUp(self, client_id, self.p4_name)
        self.getRateTime = 100
	   
        # Get bfrt_info and set it as part of the test
        bfrt_info = self.interface.bfrt_info_get(self.p4_name)
        # qid table
        self.qid_table = bfrt_info.table_get("SwitchIngress.qid")
        self.qid_table.info.key_field_annotation_add("ig_md.per_flow_hdr.fid", "ipv4")
        # register table
        self.register = bfrt_info.table_get("SwitchIngress.reg")
        # Counter
        self.counter = bfrt_info.table_get("SwitchIngress.cnt")
        # counter table
        self.cnt_table = bfrt_info.table_get("SwitchIngress.tab_cnt")
        self.cnt_table.info.key_field_annotation_add("ig_md.per_flow_hdr.fid", "ipv4")
        # get target
        self.target = gc.Target(device_id=0, pipe_id=0xffff)        

        self.flow_pkt_dict = {}
        self.flow_q_dict = {}
        self.flow_cnt_index = {}
        self.udp_flow_dict = {}
        self.udp_flow_rcv_time = {}

    def runTest(self):
        queue_weight = [0,0,0,0,0,0,0,0]

        # Set up api for control plane to data plane
        self.fixedObj = self.FixedAPIs([self.p4_name])
        # self.FixedAPIs([self.p4_name])
        self.fixedObj.setUp()

        # get the number's of pipe
        num_pipes = int(testutils.test_param_get('num_pipes'))
        print('num_pipes: %d' % num_pipes)
        last_reg_value=0
        check_time = 100
        next_counter_id = 0
        while True :
            # Get from sw and check its value
            time.sleep(0.01)
            self.register.operations_execute(self.target, 'SyncRegisters')
            resp = self.register.entry_get(
                self.target,
                [self.register.make_key([gc.KeyTuple('$REGISTER_INDEX', 0)])],
                {"from_hw": False})
            data_dict = next(resp)[0].to_dict() 
            reg_value = data_dict["SwitchIngress.reg.r_value"][1]
            
            if (reg_value == last_reg_value) or (reg_value == 0) or (self.flow_pkt_dict.get(reg_value) != None) :
                pass
            else:    
                # for i in range(num_pipes):
                #     print("data_dict %d: %d" % (i, data_dict["SwitchIngress.reg.r_value"][i]))
                print('new reg_value: %d' % reg_value)
                flow_num = 1000
                qid = 1000
                ## New UDP flow
                if reg_value > 99999:
                    fid = reg_value - 100000
                    qid = 6

                    self.flow_pkt_dict[reg_value] = 0
                    ## Write counter
                    self.flow_cnt_index[fid] = next_counter_id
                    self.write_counter(fid)
                    ## Write table 6
                    self.flow_in_queue[qid].append([fid, 0])
                    self.write_table(fid, qid)
                    ## Wait for the flow rate be calculated
                    self.udp_flow_rcv_time[fid] = self.getRateTime
                ## New TCP flow
                else:
                    fid = reg_value
                    for q in self.tcp_queue:
                        if flow_num > len(self.flow_in_queue[q]):
                            flow_num = len(self.flow_in_queue[q])
                            qid = q
                    ## Save flow ID
                    self.flow_pkt_dict[reg_value] = 0
                    ## Write counter
                    self.flow_cnt_index[fid] = next_counter_id
                    self.write_counter(fid)
                    ## Write table
                    self.flow_in_queue[qid].append([fid, 0])
                    self.write_table(fid, qid)
                last_reg_value = reg_value
                next_counter_id += 1

            ## Write UDP flow in table with rate
            for r_val in list(self.flow_pkt_dict.keys()):
                if r_val > 99999:
                    fid = r_val-100000
                    if self.udp_flow_rcv_time[fid] != 0:
                        self.udp_flow_rcv_time[fid] -= 1
                        ## Record rate and add to table
                        if self.udp_flow_rcv_time[fid] <= 0:                                    
                            counter_id = self.flow_cnt_index[fid]
                            cnt_resp = self.counter.entry_get(self.target,
                                            [self.counter.make_key(
                                                [gc.KeyTuple('$COUNTER_INDEX', counter_id)])],
                                            {"from_hw": True},
                                            None)
                            cnt_data = next(cnt_resp)[0].to_dict()
                            self.udp_flow_dict[fid] = cnt_data["$COUNTER_SPEC_PKTS"]
                            self.add_udp_flow(fid)

            ## Check for the status of flows
            check_time-=1
            if check_time <= 0:

                self.display_status()

                resp = self.qid_table.default_entry_get(self.target,
                    {"from_hw": False})
                for i in range(8):
                    queue_weight[i] = self.fixedObj.tm.tm_get_q_dwrr_weight(0,self.eg_port,i)
                print "Queue weight: ", queue_weight

                #flow counter
                for r_val in list(self.flow_pkt_dict.keys()):
                    if r_val > 99999:
                        fid = r_val-100000
                        flow_type = 'udp'
                    else:
                        fid = r_val
                        flow_type = 'tcp'

                    counter_id = self.flow_cnt_index[fid]
                    cnt_resp = self.counter.entry_get(self.target,
                                       [self.counter.make_key([gc.KeyTuple('$COUNTER_INDEX', counter_id)])],
                                       {"from_hw": True},
                                       None)
                    cnt_data = next(cnt_resp)[0].to_dict()
                    flow_pkt_new = cnt_data["$COUNTER_SPEC_PKTS"]
                    
                    print('Flow %d -> new_recv_pkts: %d; old_recv_pkts: %d' % (fid, flow_pkt_new, self.flow_pkt_dict[r_val]))
                    if flow_pkt_new > self.flow_pkt_dict[r_val]:
                        self.flow_pkt_dict[r_val] = flow_pkt_new
                    else:
                        self.del_table(fid, flow_type)
                check_time = 100

    def write_table(self, fid, qid):
        print "Add %d to Queue %d" % (fid, qid)
                
        self.flow_q_dict[fid] = qid
        self.qid_table.entry_add(
            self.target,
            [self.qid_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])],
            [self.qid_table.make_data(
            [gc.DataTuple('queue_id',qid)],
                'SwitchIngress.set_queue_id')])

        self.fixedObj.tm.tm_set_q_dwrr_weight(0,self.eg_port,qid,self.weight_base*len(self.flow_in_queue[qid]))
        
    def write_counter(self, fid):
        self.cnt_table.entry_add(
            self.target,
            [self.cnt_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])],
            [self.cnt_table.make_data(
                [gc.DataTuple('counter_id', self.flow_cnt_index[fid])],
                    'SwitchIngress.flow_count')])

    def del_table(self, fid, flow_type):
        print('delete flow %d from table' % fid)

        self.qid_table.entry_del(
            self.target,
            [self.qid_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])])

        self.cnt_table.entry_del(
            self.target,
            [self.cnt_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])])

        rate = 0
        if flow_type == 'udp':
            rate = self.udp_flow_dict[fid]
            del self.udp_flow_dict[fid]
            del self.udp_flow_rcv_time[fid]
            del self.flow_pkt_dict[fid+100000]
        else:
            del self.flow_pkt_dict[fid]

        qid = self.flow_q_dict[fid]
        self.flow_in_queue[qid].remove([fid, rate])

        if len(self.flow_in_queue[qid]) == 0:
            self.fixedObj.tm.tm_set_q_dwrr_weight(0,self.eg_port,qid,self.weight_base)
        else:
            self.fixedObj.tm.tm_set_q_dwrr_weight(0,self.eg_port,qid,self.weight_base*len(self.flow_in_queue[qid]))

        del self.flow_q_dict[fid]
        del self.flow_cnt_index[fid]

    def add_udp_flow(self, fid):
        # remove from table
        print('delete udp flow %d in queue 6 from table' % fid)
        self.qid_table.entry_del(
            self.target,
            [self.qid_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])])
        self.flow_in_queue[6].remove([fid, 0])

        rate = self.udp_flow_dict[fid]

        # if some queue is not used
        for qid in self.udp_queue:
            if not self.flow_in_queue[qid]:
                # self.recreate_table()
                self.flow_in_queue[qid].append([fid, rate])
                self.write_table(fid, qid)
                self.queue_interval[qid-self.udp_queue[0]] = [rate, rate]
                print("Set flow %d with rate %d to queue %d" % (fid, rate, qid))
                return
        for qid in self.udp_queue:
            itv = self.queue_interval[qid-self.udp_queue[0]]
            if rate < itv[0] or (qid == self.udp_queue[-1] and rate > itv[1]):
                self.recreate_table()
                return
            elif itv[0] <= rate <= itv[1]:
                self.flow_in_queue[qid].append([fid, rate])
                self.write_table(fid, qid)
                print("Set flow %d with rate %d to queue %d" % (fid, rate, qid))
                break

    def recreate_table(self):
        step = []

        udp_flows = []

        for fid, rate in self.udp_flow_dict.iteritems():
            udp_flows.append([fid, rate])

        udp_flows.sort(key=lambda k: k[1])
        
        i = 1
        while i < len(udp_flows):
            step.append(udp_flows[i][1] - udp_flows[i-1][1])
            i += 1
        # print(self.flows)
        # print(step)

        s = sorted(range(len(step)), key=lambda k: step[k])

        split_pos = sorted(s[max(0, len(s)-len(self.udp_queue)+1):len(s)])
        split_pos.append(len(udp_flows)-1)

        # clean UDP flows in table
        self.clear_udp_from_table()

        print "Split position: ", split_pos

        left = 0
        count = 0
        for right in split_pos:
            qid = count + self.udp_queue[0]
            self.flow_in_queue[qid] = udp_flows[left:right+1]

            self.queue_interval[count] = [udp_flows[left][1], udp_flows[right][1]]
            for flow in self.flow_in_queue[qid]:
                fid = flow[0]
                ## Write table
                self.write_table(fid, qid)

            left = right+1
            count += 1
        
        for i in self.udp_queue:
            print "UDP Queue %d: " % i, self.flow_in_queue[i]

    def clear_udp_from_table(self):
        for i in self.udp_queue:
            for flow in self.flow_in_queue[i]:
                fid = flow[0]
                qid = self.flow_q_dict[fid]
                self.qid_table.entry_del(
                    self.target,
                    [self.qid_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])])
                print "Clear %d from Queue %d" % (fid, qid)

    def display_status(self):
        print "===== Basic status ====="
        print "Flow in Queue"
        for i in range(len(self.flow_in_queue)):
            print "Queue %d: " % i, self.flow_in_queue[i]
        
        print "Flow pkt dict (100000 base):", self.flow_pkt_dict
        print "Flow q dict:", self.flow_q_dict
        print "Flow cnt index:", self.flow_cnt_index

    def display_udp_status(self):
        print "===== UDP info ====="
        print "UDP flow dict:", self.udp_flow_dict
        print "UDP flow rcv time:", self.udp_flow_rcv_time
        print "Interval of UDP queue:", self.queue_interval
        # Here start to reset

            

