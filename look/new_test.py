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

#    def __init__(self):
    def setUp(self):
        client_id = 0
        BfRuntimeTest.setUp(self, client_id, self.p4_name)
    	
        self.p4_name = "per_flow_q"
    	self.eg_port = 273 #h2
    	self.flow_in_queue = [[],[],[],[],[],[],[],[]]
    	self.queue_interval = [[],[],[],[]]
    	self.tcp_queue = range(0,3)
    	self.udp_queue = range(3,7)

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
    	self.upd_flow_rcv_time = {}

        
    def runTest(self):
    	queue_weight = [0,0,0,0,0,0,0,0]
        
        # Set up api for control plane to data plane
        self.fixedObj = self.FixedAPIs(["per_flow_q"])
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
            
            if (reg_value == last_reg_value) or (reg_value == 0) or (self.flow_q_dict.get(str(reg_value)) != None) :
                pass
            else:    
                for i in range(num_pipes):
                    print("data_dict %d: %d" % (i, data_dict["SwitchIngress.reg.r_value"][i]))
                print('new reg_value: %d' % reg_value)
                flow_num = 1000
                index = 1000
                # new UDP flow
                if reg_value > 99999:
               	    fid = reg_value - 100000
                    # select queue with less flow
                    for i in self.udp_queue:
                        if flow_num > len(self.flow_in_queue[i]):
                            flow_num = len(self.flow_in_queue[i])
                            index = i
                    if index in self.udp_queue:                        
                        last_reg_value = reg_value #return to the read value
                        self.flow_pkt_dict[str(last_reg_value)] = 0
                        self.flow_cnt_index[str(last_reg_value)] = next_counter_id
                        self.upd_flow_rcv_time[fid] = 10
                        next_counter_id += 1
                    else:
                        print('index value error')
                # new TCP flow
                else:
               	    fid = reg_value
                    for i in self.tcp_queue:
                        if flow_num > len(self.flow_in_queue[i]):
                            flow_num = len(self.flow_in_queue[i])
                            index = i
                    if index in self.tcp_queue:                        
                        last_reg_value = reg_value #save the read value
                        self.flow_q_dict[str(last_reg_value)] = index
                        self.flow_pkt_dict[str(last_reg_value)] = 0
                        self.flow_cnt_index[str(last_reg_value)] = next_counter_id
                        self.write_table(fid, index)
                        next_counter_id += 1
                    else:
                        print('index value error')
            check_time-=1
            if check_time <= 0:
                print('show info') 
                #queue info
                print('flow_in_queue: ',len(self.flow_in_queue))
                resp = self.qid_table.default_entry_get(self.target,
                    {"from_hw": False})
                for i in range(8):
                    queue_weight[i] = self.fixedObj.tm.tm_get_q_dwrr_weight(0,self.eg_port,i)
                print("queue_weight: ")
                print(queue_weight)
                print(self.flow_q_dict)
                print(self.flow_pkt_dict)
                #flow counter
                for k in list(self.flow_pkt_dict.keys()):    
                    qid = self.flow_q_dict[k]
                    fid = int(k)
                    flow_type = 'tcp'
                    if fid > 99999:
                        fid-=100000
                        flow_type = 'udp'
                    counter_id = self.flow_cnt_index[k]
                    cnt_resp = counter.entry_get(self.target,
                                       [counter.make_key([gc.KeyTuple('$COUNTER_INDEX', counter_id)])],
                                       {"from_hw": True},
                                       None)
                    cnt_data = next(cnt_resp)[0].to_dict()
                    flow_pkt_new = cnt_data["$COUNTER_SPEC_PKTS"]
                    flow_pkt_old = self.flow_pkt_dict[k]

                    if self.udp_flow_rcv_time[str(fid)] != 0:
                    	self.udp_flow_rcv_time[str(fid)] -= 1
                    	if self.udp_flow_rcv_time[str(fid)] == 0:
                    		self.udp_flow_dict[fid] = flow_pkt_new
                    		self.add_udp_flow()
                    
                    print(k,'new_recv_pkts: ',self.flow_pkt_new,'old_recv_pkts: ',self.flow_pkt_old)
                    if flow_pkt_new > flow_pkt_old:
                        self.flow_pkt_dict[k] = flow_pkt_new
                    else:
                        self.del_table(fid, flow_type)
                check_time = 50

    def write_table(self, fid, flow_type):
    	if flow_type == 'udp':
            qid = self.flow_q_dict[fid + 100000]
        else:
            qid = self.flow_q_dict[fid]

    	self.qid_table.entry_add(
            self.target,
            [self.qid_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])],
            [self.qid_table.make_data(
            [gc.DataTuple('queue_id',qid)],
                'SwitchIngress.set_queue_id')])

        self.flow_in_queue[qid].append([fid, 0])
        self.fixedObj.tm.tm_set_q_dwrr_weight(0,self.eg_port,qid,200*len(self.flow_in_queue[qid]))
        
        self.cnt_table.entry_add(
            self.target,
            [self.cnt_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])],
            [self.cnt_table.make_data(
                [gc.DataTuple('counter_id', self.flow_cnt_index[fid])],
                    'SwitchIngress.flow_count')])

    def del_table(self, fid, flow_type):
       	print('flow ',fid ,' is end, delete')

    	self.qid_table.entry_del(
        	self.target,
        	[self.qid_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])])
         
        self.cnt_table.entry_del(
            self.target,
            [self.cnt_table.make_key([gc.KeyTuple("ig_md.per_flow_hdr.fid", fid)])])        

        if flow_type == 'udp':
        	del self.udp_flow_dict[fid]
        	del self.udp_flow_rcv_time[fid]
        	fid += 100000
    	qid = self.flow_q_dict[fid]

        if len(self.flow_in_queue[qid]) == 0:
            self.fixedObj.tm.tm_set_q_dwrr_weight(0,self.eg_port,qid,200)
        else:
        	self.fixedObj.tm.tm_set_q_dwrr_weight(0,self.eg_port,qid,200*len(self.flow_in_queue[qid]))

        del self.flow_q_dict[fid]
        del self.flow_pkt_dict[fid]
        del self.flow_cnt_index[fid]

	def add_udp_flow(self, fid, rate, next_counter_id):
	    self.udp_flow_dict[fid] = rate
	    for i in self.udp_queue:
	    	if not self.flow_in_queue[i]:
	        	self.recreate_table()
	        	return
	    for idx in self.udp_queue:
	    	itv = self.queue_interval[idx-3]
	    	if newFlow[1] < itv[0] or (idx == self.udp_queue[-1] and rate > itv[1]):
	        	self.recreate_table()
	        	return
        	elif itv[0] <= newFlow[1] <= itv[1]:
	        	self.flow_in_queue[idx].append(newFlow)
	        	self.write_table(newFlow[1], idx, next_counter_id)
	        	print("Set flow (%s, %d) to queue %d" % (newFlow[0], newFlow[1], idx))
	        	break

	def clear_udp_from_table(self):
		for key, value in udp_flow_dict.iteritems():
			if value != 0:
				self.del_table(key, 'udp')

    def recreate_table(self):
	    step = []
	    udp_flow_in_queue = [[],[],[],[]]

	    udp_flows = []

	    for key, value in udp_flow_dict.iteritems():
	    	if value != 0:
		    	temp = [key, value]
		    	udp_flows.append(temp)

	    udp_flows.sort(key=lambda k: k[1])
	    print(udp_flows)
	    
	    i = 1
	    while i < len(self.upd_flows):
	    	step.append(self.udp_flows[i][1] - self.flows[i-1][1])
	    	i += 1
	    # print(self.flows)
	    # print(step)

	    s = sorted(range(len(step)), key=lambda k: step[k])

	    split_pos = sorted(s[max(0, len(s)-len(self.udp_queue)+1):len(s)])
	    
	    # clean UDP flows in table
	    self.clear_udp_from_table()        

	    left = 0
	    count = 0
	    for right in split_pos:
      		udp_flow_in_queue[count] = self.udp_flows[left:right+1]
      		# print("Queue", count, ":", self.flows[left:right+1])
      		self.queue_interval[count] = [self.udp_flows[left][1], self.udp_flows[right][1]]
      		for fid in udp_flow_in_queue[count]:
                    self.flow_q_dict[fid+100000] = count + self.udp_queue[0]
                    self.write_table(fid, 'udp')

      		left = right+1
      		count += 1
	    udp_flow_in_queue[count] = self.flows[left:len(self.flows)]
	    self.queue_interval[count] = [(self.flows[left][1]), self.flows[len(self.flows)-1][1]]
            for fid in udp_flow_in_queue[count]:
    	        self.flow_q_dict[fid+100000] = count + self.udp_queue[0]
                self.write_table(fid, 'udp')

	    self.flow_in_queue = queue
	    print(self.queue_interval)

            

