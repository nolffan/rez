# unshield 1.5.1 (https://github.com/twogood/unshield, MIT -- see LICENSE),
# vendored so the InstallShield cabinets can be unpacked without CMake or a
# system package. Builds one static binary: tools/unshield/unshield.
CC ?= cc
CFLAGS ?= -O2
CFLAGS += -std=gnu99 -DHAVE_CONFIG_H -I. -Ilib -Wno-unused-result
LIB = lib/bswap.c lib/component.c lib/directory.c lib/file.c lib/file_group.c \
      lib/helper.c lib/libunshield.c lib/log.c \
      lib/convert_utf/ConvertUTF.c lib/md5/md5c.c

all: unshield unshield-deobfuscate

unshield: src/unshield.c $(LIB) $(wildcard lib/*.h)
	$(CC) $(CFLAGS) -o $@ src/unshield.c $(LIB) -lz

clean:
	rm -f unshield unshield-deobfuscate
.PHONY: all clean

unshield-deobfuscate: src/unshield-deobfuscate.c $(LIB) $(wildcard lib/*.h)
	$(CC) $(CFLAGS) -o $@ src/unshield-deobfuscate.c $(LIB) -lz
