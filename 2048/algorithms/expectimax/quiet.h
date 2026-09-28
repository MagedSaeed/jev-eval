// Force-included by build.sh: 2048-ai prints the board and a line per candidate move to stdout,
// which would flood play.py's progress bars. Only printf is silenced; the algorithm is untouched.
#include <cstdio>
#define printf(...) ((void)0)
