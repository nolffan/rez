/* blast.c -- decompress PKWARE Data Compression Library ("implode") streams.
 *
 * A re-statement of Mark Adler's zlib contrib/blast.c algorithm.
 *
 *   blast <in> <offset> <out>    decode the stream starting at <offset>;
 *                                prints the number of input bytes consumed
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAXBITS 13
#define MAXWIN 4096

static FILE *in;                 /* read from the stream's offset on */
static unsigned char ibuf[65536];
static size_t ilen, ipos, inpos;  /* inpos: bytes of the stream taken */
static int bitbuf, bitcnt;
static unsigned char win[MAXWIN];
static unsigned winpos;
static int wrapped;
static FILE *out;
static unsigned char obuf[65536];
static size_t opos;
static long long total;

static void flush_out(void) { fwrite(obuf, 1, opos, out); opos = 0; }

static int next_byte(void)
{
    if (ipos == ilen) {
        ilen = fread(ibuf, 1, sizeof ibuf, in);
        ipos = 0;
        if (ilen == 0) { fprintf(stderr, "blast: out of input\n"); exit(2); }
    }
    inpos++;
    return ibuf[ipos++];
}
static void put(int c)
{
    win[winpos++] = c;
    if (winpos == MAXWIN) { winpos = 0; wrapped = 1; }
    obuf[opos++] = c;
    if (opos == sizeof obuf) flush_out();
    total++;
}

static int bits(int need)
{
    int val = bitbuf;
    while (bitcnt < need) {
        val |= next_byte() << bitcnt;
        bitcnt += 8;
    }
    bitbuf = val >> need;
    bitcnt -= need;
    return val & ((1 << need) - 1);
}

struct huffman { short count[MAXBITS + 1]; short symbol[256]; };

static int decode(const struct huffman *h)
{
    int code = 0, first = 0, index = 0, len = 1, count;
    int bitbuf_ = bitbuf, left = bitcnt;
    const short *next = h->count + 1;
    for (;;) {
        while (left--) {
            code |= (bitbuf_ & 1) ^ 1;   /* codes are stored inverted */
            bitbuf_ >>= 1;
            count = *next++;
            if (code < first + count) {
                bitbuf = bitbuf_;
                bitcnt = (bitcnt - len) & 7;
                return h->symbol[index + (code - first)];
            }
            index += count;
            first += count;
            first <<= 1;
            code <<= 1;
            len++;
        }
        left = (MAXBITS + 1) - len;
        if (left == 0) break;
        bitbuf_ = next_byte();
        if (left > 8) left = 8;
    }
    return -9;
}

static void construct(struct huffman *h, const unsigned char *rep, int n)
{
    short length[256], offs[MAXBITS + 1];
    int symbol = 0, len, left;
    do {
        len = *rep++;
        left = (len >> 4) + 1;
        len &= 15;
        do length[symbol++] = len; while (--left);
    } while (--n);
    n = symbol;
    memset(h->count, 0, sizeof h->count);
    for (symbol = 0; symbol < n; symbol++) h->count[length[symbol]]++;
    offs[1] = 0;
    for (len = 1; len < MAXBITS; len++) offs[len + 1] = offs[len] + h->count[len];
    for (symbol = 0; symbol < n; symbol++)
        if (length[symbol] != 0) h->symbol[offs[length[symbol]]++] = symbol;
}

int main(int argc, char **argv)
{
    static const unsigned char litlen[] = {
        11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8,
        9, 7, 6, 7, 8, 7, 6, 55, 8, 23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5,
        7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9, 8, 25, 11, 8, 11, 9, 12,
        8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10, 27,
        44, 253, 253, 253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45,
        44, 173};
    static const unsigned char lenlen[] = {2, 35, 36, 53, 38, 23};
    static const unsigned char distlen[] = {2, 20, 53, 230, 247, 151, 248};
    static const short base[16] = {3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264};
    static const char extra[16] = {0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8};
    struct huffman litcode, lencode, distcode;
    int lit, dict, symbol, len;
    unsigned dist;

    if (argc != 4) { fprintf(stderr, "usage: blast <in> <offset> <out>\n"); return 1; }
    in = fopen(argv[1], "rb");
    if (!in) { perror(argv[1]); return 1; }
    if (fseek(in, strtol(argv[2], NULL, 0), SEEK_SET)) { perror("seek"); return 1; }
    out = fopen(argv[3], "wb");
    if (!out) { perror(argv[3]); return 1; }

    construct(&litcode, litlen, sizeof litlen);
    construct(&lencode, lenlen, sizeof lenlen);
    construct(&distcode, distlen, sizeof distlen);

    lit = bits(8);
    if (lit > 1) { fprintf(stderr, "blast: bad literal flag\n"); return 2; }
    dict = bits(8);
    if (dict < 4 || dict > 6) { fprintf(stderr, "blast: bad dictionary size\n"); return 2; }

    do {
        if (bits(1)) {
            symbol = decode(&lencode);
            len = base[symbol] + bits(extra[symbol]);
            if (len == 519) break;              /* end code */
            symbol = len == 2 ? 2 : dict;
            dist = decode(&distcode) << symbol;
            dist += bits(symbol);
            dist++;
            if (!wrapped && dist > winpos) { fprintf(stderr, "blast: distance too far\n"); return 2; }
            while (len--) put(win[(winpos - dist) & (MAXWIN - 1)]);
        } else {
            symbol = lit ? decode(&litcode) : bits(8);
            put(symbol);
        }
    } while (1);
    flush_out();
    fclose(out);
    printf("%zu %lld\n", inpos, total);
    return 0;
}
