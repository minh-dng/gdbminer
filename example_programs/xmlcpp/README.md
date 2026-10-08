## Compile statically and with debug

  clang++ -g -O0 -o xmlcpp xml.cpp 
  
## Debug 
  gdb --args ./xmlcpp ../yxml/seeds/seed.1.in