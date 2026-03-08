#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sameshi.h"

static int piece_from_fen(char c) {
    switch (c) {
    case 'P': return 1;
    case 'N': return 2;
    case 'B': return 3;
    case 'R': return 4;
    case 'Q': return 5;
    case 'K': return 6;
    case 'p': return -1;
    case 'n': return -2;
    case 'b': return -3;
    case 'r': return -4;
    case 'q': return -5;
    case 'k': return -6;
    default: return 0;
    }
}

static void clear_board(void) {
    for (int i = 0; i < 120; i++) {
        int rr = i / 10;
        int cc = i % 10;
        b[i] = (rr < 2 || rr > 9 || cc < 1 || cc > 8) ? 7 : 0;
    }
}

static int load_fen(const char *fen, int *side_to_move) {
    clear_board();

    int rank = 8;
    int file = 1;
    int i = 0;

    while (fen[i] && fen[i] != ' ') {
        char c = fen[i++];

        if (c == '/') {
            rank--;
            file = 1;
            continue;
        }

        if (c >= '1' && c <= '8') {
            file += c - '0';
            continue;
        }

        int piece = piece_from_fen(c);
        if (!piece || rank < 1 || rank > 8 || file < 1 || file > 8) {
            return 0;
        }

        int sq = (rank + 1) * 10 + file;
        b[sq] = piece;
        file++;
    }

    if (fen[i] != ' ') {
        return 0;
    }
    i++;

    if (fen[i] == 'w') {
        *side_to_move = 1;
    } else if (fen[i] == 'b') {
        *side_to_move = -1;
    } else {
        return 0;
    }

    return 1;
}

static int push_root_move(int s, int d, int *a, int be, int u, int t, int p, int x, int *m,
                          int *best_from, int *best_to) {
    int moved_before = *m;
    int old_a = *a;
    int next_a = E(s, d, *a, be, u, t, p, x, m);

    if ((next_a > old_a || (!moved_before && *m)) && *best_from == 0) {
        *best_from = u;
        *best_to = t;
    }
    if (next_a > old_a) {
        *best_from = u;
        *best_to = t;
    }

    *a = next_a;
    return *a >= be;
}

static int search_root(int s, int d, int a, int be, int *best_from, int *best_to) {
    int m = 0;
    *best_from = 0;
    *best_to = 0;

    for (int z = 0; z < 2; z++) {
        for (int u = 21; u < 99; u++) {
            int p = b[u];
            if (p == 7 || !p || ((p > 0) != (s > 0))) {
                continue;
            }

            int g = j(p);
            if (g == 1) {
                int o = s == 1 ? 10 : -10;
                if (!z) {
                    for (int i = -1; i <= 1; i += 2) {
                        int t = u + o + i;
                        int x = b[t];
                        if (x && x != 7 && ((x > 0) != (s > 0))) {
                            if (push_root_move(s, d, &a, be, u, t, p, x, &m, best_from,
                                               best_to)) {
                                return be;
                            }
                        }
                    }
                } else if (!b[u + o]) {
                    int t = u + o;
                    if (push_root_move(s, d, &a, be, u, t, p, 0, &m, best_from, best_to)) {
                        return be;
                    }

                    if (((s == 1 && u < 40) || (s == -1 && u > 70)) && !b[u + 2 * o]) {
                        t = u + 2 * o;
                        if (push_root_move(s, d, &a, be, u, t, p, 0, &m, best_from,
                                           best_to)) {
                            return be;
                        }
                    }
                }
                continue;
            }

            int *w = K;
            int st = 0;
            int en = 8;
            if (g == 2) {
                w = N;
            } else if (g == 4) {
                en = 4;
            } else if (g == 3) {
                st = 4;
            }

            for (int i = st; i < en; i++) {
                int o = w[i];
                int t = u;
                int slide = (g != 2 && g != 6);

                while (1) {
                    t += o;
                    int tg = b[t];
                    if (tg == 7) {
                        break;
                    }
                    if (tg && ((tg > 0) == (s > 0))) {
                        break;
                    }

                    if (!z) {
                        if (tg) {
                            if (push_root_move(s, d, &a, be, u, t, p, tg, &m, best_from,
                                               best_to)) {
                                return be;
                            }
                            break;
                        }
                    } else {
                        if (!tg) {
                            if (push_root_move(s, d, &a, be, u, t, p, 0, &m, best_from,
                                               best_to)) {
                                return be;
                            }
                        } else {
                            break;
                        }
                    }

                    if (!slide) {
                        break;
                    }
                }
            }
        }
    }

    if (!m) {
        return C(s) ? -9999 : 0;
    }
    return a;
}

static void print_move_uci(int from, int to) {
    if (from <= 0 || to <= 0) {
        puts("0000");
        return;
    }

    char ff = (char)('a' + (from % 10) - 1);
    char fr = (char)('0' + (from / 10) - 1);
    char tf = (char)('a' + (to % 10) - 1);
    char tr = (char)('0' + (to / 10) - 1);
    printf("%c%c%c%c\n", ff, fr, tf, tr);
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fputs("usage: sameshi_bridge \"<fen>\" <depth>\n", stderr);
        return 1;
    }

    const char *fen = argv[1];
    int depth = atoi(argv[2]);
    if (depth < 1) {
        depth = 1;
    }
    if (depth > 6) {
        depth = 6;
    }

    int side = 1;
    if (!load_fen(fen, &side)) {
        puts("0000");
        return 2;
    }

    int best_from = 0;
    int best_to = 0;
    search_root(side, depth, -30000, 30000, &best_from, &best_to);
    print_move_uci(best_from, best_to);

    return 0;
}
