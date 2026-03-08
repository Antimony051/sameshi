CC=gcc
CFLAGS=-Wall -O3 -std=c99 -s -Wno-unused-result -Wno-parentheses
LDFLAGS=-lm

all: sameshi sameshi_bridge

sameshi: main.c sameshi.h
	$(CC) $(CFLAGS) main.c -o sameshi $(LDFLAGS)

sameshi_bridge: bridge.c sameshi.h
	$(CC) $(CFLAGS) bridge.c -o sameshi_bridge $(LDFLAGS)

run: sameshi
	./sameshi

run-bridge: sameshi_bridge
	./sameshi_bridge "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1" 4

clean:
	rm -f sameshi sameshi_bridge
