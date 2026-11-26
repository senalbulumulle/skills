# hybrid-llms - build with `make`, install with `make install` (PREFIX=~/.local by default).
# Portable C11 + POSIX threads; no third-party libraries. Works with Apple clang and gcc.

CC      ?= cc
PREFIX  ?= $(HOME)/.local
BINDIR  ?= $(PREFIX)/bin
CFLAGS  ?= -O2
CFLAGS  += -std=c11 -Wall -Wextra -Wshadow -Wno-unused-parameter -D_DARWIN_C_SOURCE -D_DEFAULT_SOURCE -Isrc
LDLIBS  += -lpthread -lm

SRCS := src/util.c src/json.c src/config.c src/http.c src/proc.c src/engine.c src/local.c \
        src/cloud.c src/hybrid.c src/mcp.c src/server.c
OBJS := $(SRCS:src/%.c=build/%.o)
BIN  := build/hybrid-llms

.PHONY: all clean install uninstall test debug check

all: $(BIN)

build:
	mkdir -p build

build/%.o: src/%.c src/*.h | build
	$(CC) $(CFLAGS) -c $< -o $@

$(BIN): $(OBJS) build/main.o
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

# Compile-only check of every source (no binary is run).
check:
	@for f in $(SRCS) src/main.c tests/test_units.c; do \
		$(CC) $(CFLAGS) -Werror -fsyntax-only $$f || exit 1; \
	done
	@echo "check: ok"

debug: clean
	$(MAKE) CFLAGS="-O0 -g -fsanitize=address,undefined" LDFLAGS="-fsanitize=address,undefined"

build/test_units: tests/test_units.c $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

test: $(BIN) build/test_units
	./build/test_units
	sh tests/test_mcp.sh ./$(BIN)

install: $(BIN)
	mkdir -p "$(BINDIR)"
	install -m 0755 $(BIN) "$(BINDIR)/hybrid-llms"

uninstall:
	rm -f "$(BINDIR)/hybrid-llms"

clean:
	rm -rf build
