set pagination off
set confirm off
set remotetimeout 10
target extended-remote :3334
monitor reset halt
thbreak parse_xml
python open('/Users/dan173/Documents/Uni/thesis/impl/gdbminer.esp32-c3/docs/thesis/esp32c3-hardware-watchpoints-2026-09-28/send-input', 'w').close()
continue
printf "PARSER_ENTRY pc=%p\n", $pc
thbreak *0x42000064
continue
printf "BEFORE_LOAD pc=%p address=%p value=%u\n", $pc, $a5, *(unsigned char*)$a5
x/i $pc
rwatch -location *(unsigned char*)$a5
python
hits=[]
def stopped(event):
    if isinstance(event, gdb.BreakpointEvent):
        hits.extend(b.type for b in event.breakpoints if b.type == gdb.BP_READ_WATCHPOINT)
gdb.events.stop.connect(stopped)
end
stepi
printf "AFTER_LOAD pc=%p value=%u\n", $pc, $a5
python print("HARDWARE_READ_WATCHPOINT_HITS=" + str(len(hits)))
delete breakpoints
monitor reset run
detach
quit
