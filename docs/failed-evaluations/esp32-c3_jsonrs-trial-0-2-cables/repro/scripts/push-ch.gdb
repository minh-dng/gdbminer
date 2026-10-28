set pagination off
set confirm off
target extended-remote :3333
set language c
set print frame-arguments none
hbreak *0x4200963a
shell touch /tmp/c3pm/go
continue
echo \n--- raw argument slots at entry ($sp+24 self, $sp+28 ch)\n
x/2wx $sp+24
echo --- self\n
print self
echo --- ch as an integer\n
print/x ch
echo --- ch as a character\n
print ch
echo \n--- survived\n
delete
detach
