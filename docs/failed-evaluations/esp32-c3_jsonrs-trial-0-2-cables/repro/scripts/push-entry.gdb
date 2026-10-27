set pagination off
set confirm off
target extended-remote :3333
set language c
set print frame-arguments none
hbreak *0x4200963a
shell touch /tmp/c3pm/go
continue
echo \n--- stopped at String::push entry (frame-arguments none)\n
info registers pc sp a0 a1
echo --- DWARF locations of the arguments\n
info scope *0x4200963a
echo --- the stack slots those locations name, not yet written at entry\n
x/4wx $sp+8
echo --- now print the arguments as the default (scalars) stop record does\n
set print frame-arguments scalars
frame
echo \n--- survived\n
delete
detach
