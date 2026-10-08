## Compile statically and with debug

  clang -g -O0 -o cgi_decode cgi_decode.c 
  
## Debug 
  gdb --args ./cgi_decode seeds/seed.1.in