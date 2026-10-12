// Builds a Lichess analysis-board URL for a board-only FEN (piece
// placement only, no side-to-move/castling/en-passant/move-counter
// fields -- see chess-fen.js's own header comment on where that FEN comes
// from).
//
// Lichess's analysis route is "/analysis/<FEN>", where <FEN> is the FULL,
// space-separated FEN with its "/"-separated ranks kept literally as "/"
// and the spaces percent-encoded as "%20" -- there is no "/standard/"
// segment in front of it. Verified against the live site both ways:
//
//   https://lichess.org/analysis/2rr2k1/pp1qnppp/2n1p3/3p4/1bPP3P/1P2RNP1/PB3P2/1BRQ2K1%20w%20-%20-%200%201
//   loads the full position ("fen":"2rr2k1/pp1qnppp/2n1p3/3p4/1bPP3P/1P2RNP1/PB3P2/1BRQ2K1 w - - 0 1").
//
//   https://lichess.org/analysis/standard/2rr2k1_pp1qnppp_2n1p3_3p4_1bPP3P_1P2RNP1_PB3P2_1BRQ2K1_w_-_-_0_1
//   (this module's previous, wrong construction: "/" replaced by "_",
//   under an unnecessary "/standard/" segment) returns HTTP 200 but
//   Lichess's router only recognizes the piece-placement field before the
//   first "_" it doesn't understand as a rank separator, so everything
//   after the first "_" is silently dropped and the board loads as
//   "2rr2k1/8/8/8/8/8/8/8 w - - 0 1" -- a broken position with a
//   passing-looking HTTP status.
//
// The corpus never records whose move it was (FenTT itself dropped that
// field too), so "w" is a stated assumption, not salvaged data -- the
// conventional default, and the same simplification the original
// extension made.
export function lichessAnalysisUrl(boardFen) {
  return "https://lichess.org/analysis/" + boardFen + "%20w%20-%20-%200%201";
}
