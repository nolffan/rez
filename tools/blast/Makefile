# blast: decodes the PKWARE DCL "implode" streams Setup Factory 6 installers
# are made of (tools/sfextract.py runs it). A re-statement of Mark Adler's
# zlib contrib/blast.c. Builds tools/blast/blast.
CC ?= cc
CFLAGS ?= -O2

blast: blast.c
	$(CC) $(CFLAGS) -o $@ blast.c

clean:
	rm -f blast
.PHONY: clean
