## Compile statically and with debug

  clang -g -O0 -o yxml yxml.c 
  
## Debug 
  gdb --args ./yxml seeds/seed.1.in