#include <core.p4>
#if __TARGET_TOFINO__ == 2
#include <t2na.p4>
#else
#include <tna.p4>
#endif

#include "common/headers.p4"
#include "common/util.p4"

header per_flow_h{ 
    bit<32> fid;
    bit<8> qid;
    bit<32> qdepth;
}

struct header_t {
    ethernet_h ethernet;
    vlan_tag_h vlan;
    ipv4_h ipv4;
    tcp_h tcp;
    udp_h udp;
    per_flow_h per_flow_hdr;
    }

struct reg_value{
    bit<32> r_value;
    }

struct metadata_t {
    bit<16> port1;
    bit<16> port2;
    bit<1> is_tcp;
    per_flow_h per_flow_hdr;
    bit<1> tcp_ack;
    }
// ---------------------------------------------------------------------------
// Ingress parser
// ---------------------------------------------------------------------------
parser SwitchIngressParser(
        packet_in pkt,
        out header_t hdr,
        out metadata_t ig_md,
        out ingress_intrinsic_metadata_t ig_intr_md) {

    TofinoIngressParser() tofino_parser;

    state start {
        tofino_parser.apply(pkt, ig_intr_md);
        transition parse_ethernet;
    }

    state parse_ethernet{
        pkt.extract(hdr.ethernet);
        transition select (hdr.ethernet.ether_type) {
            ETHERTYPE_IPV4 : parse_ipv4;
            ETHERTYPE_VLAN: parse_vlan;
            default : reject;
        }
    }

    state parse_vlan {
        pkt.extract(hdr.vlan);
        transition select (hdr.vlan.ether_type) {
            ETHERTYPE_IPV4 : parse_ipv4;
            default : reject;
        }
    }

    state parse_ipv4 {
        pkt.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol) {
            IP_PROTOCOLS_UDP : parse_udp;
            IP_PROTOCOLS_TCP : parse_tcp;
            default : reject;
        }
    }

   state parse_udp {
        pkt.extract(hdr.udp);
        ig_md.port1 = hdr.udp.src_port;
        ig_md.port2 = hdr.udp.dst_port;
        ig_md.is_tcp = 0;
        transition accept;
    }

    state parse_tcp {
        pkt.extract(hdr.tcp);
        ig_md.port1 = hdr.tcp.src_port;
        ig_md.port2 = hdr.tcp.dst_port;
        ig_md.is_tcp = 1;
        transition accept;
    }
    
}

// ---------------------------------------------------------------------------
// Ingress Deparser
// ---------------------------------------------------------------------------
control SwitchIngressDeparser(
        packet_out pkt,
        inout header_t hdr,
        in metadata_t ig_md,
        in ingress_intrinsic_metadata_for_deparser_t ig_intr_dprsr_md) {

    apply {
       pkt.emit(hdr);
    }
}

control SwitchIngress(
        inout header_t hdr,
        inout metadata_t ig_md,
        in ingress_intrinsic_metadata_t ig_intr_md,
        in ingress_intrinsic_metadata_from_parser_t ig_intr_prsr_md,
        inout ingress_intrinsic_metadata_for_deparser_t ig_intr_dprsr_md,
        inout ingress_intrinsic_metadata_for_tm_t ig_intr_tm_md) {

    Hash<bit<16>>(HashAlgorithm_t.CRC16) flow_id_hasher;

    Register<reg_value,bit<32>>(32w1024) reg; // Direct Register
    RegisterAction<reg_value, bit<32>,bit<32>>(reg)
    new_flow_reg_action = {
        void apply(inout reg_value value){
       if(ig_md.is_tcp == 1){
                    value.r_value = ig_md.per_flow_hdr.fid;
            }
       if(ig_md.is_tcp == 0){
                    value.r_value = ig_md.per_flow_hdr.fid + 100000;
            }
        }
    };
    
    Counter<bit<32>, bit<9>>(512, CounterType_t.PACKETS) cnt; // Indirect Counter


    action set_eg_port(PortId_t eg_port){
	ig_intr_tm_md.ucast_egress_port = eg_port;
    }

    action miss() {
        ig_intr_dprsr_md.drop_ctl = 0x1; // Drop packet
    }

    table forward {
        key = {
            hdr.ethernet.dst_addr : exact;
        }

        actions = {
            set_eg_port;
            @defaultonly miss;
        }
        default_action = miss();
        size = 1024;     
    }
    
    action hash(){
       ig_md.per_flow_hdr.fid[15:0] = flow_id_hasher.get({
                 hdr.ipv4.src_addr[31:0]
                ,hdr.ipv4.dst_addr[31:0],
                 hdr.ipv4.protocol[7:0],
                 ig_md.port1[15:0],
                 ig_md.port2[15:0]
                 });
       //ig_md.per_flow_hdr.fid[15:0] = ig_md.port2[15:0];
    }

    table tab_hash{
        actions = {
                hash;
            }
        const default_action = hash();
     }

    action set_queue_id(bit<5> queue_id){  
	ig_intr_tm_md.qid = queue_id;
    }

    action new_flow_income(){
       	ig_intr_tm_md.qid = 7;
	new_flow_reg_action.execute(0);
    }

    table qid{
        key = {
            ig_md.per_flow_hdr.fid : exact;
        }
        actions = {
            set_queue_id;
            @defaultonly new_flow_income;
        }
        default_action = new_flow_income();
        size = 512;
    }

    	
    action flow_count(bit<9> counter_id){  
		cnt.count(counter_id);
    }


    action nop(){
    }

    table tab_cnt{
        key = {
            ig_md.per_flow_hdr.fid : exact;
        }
        actions = {
            	flow_count;
		@defaultonly nop;
        }
        default_action = nop;
        size = 1024;
    }
    apply {
        ig_md.per_flow_hdr.fid = 32w0;
        forward.apply();
	    if(ig_intr_tm_md.ucast_egress_port == 59){
		    tab_hash.apply();
        	qid.apply();
		    tab_cnt.apply();
	    }
	    ig_intr_tm_md.bypass_egress = 1w1;
    }
}

Pipeline(SwitchIngressParser(),
         SwitchIngress(),
         SwitchIngressDeparser(),
         EmptyEgressParser(),
         EmptyEgress(),
         EmptyEgressDeparser()) pipe;

Switch(pipe) main;
