// Mounts a view-only chessground board (https://github.com/lichess-org/chessground,
// GPL-3.0, vendored under /vendor/chessground/) into every element with
// class "chess-fen" that HtmlRewrite.scala left in the page body, reading
// the position from its data-fen attribute.
//
// That attribute holds the corpus's original <fentt> tag body -- almost
// always a clean board-only FEN (the piece-placement field only, no
// side-to-move/castling/en-passant/move-counter fields), salvaged from the
// wiki's old FenTT MediaWiki extension (legacy/extensions/FenTT/). FenTT's
// modified-FEN alphabet also let a diagram mark squares with (), [], {}
// highlights or stand-alone "+"/"x"/"." annotation marks that aren't valid
// FEN at all -- a handful of this corpus's tags (board-geometry
// illustrations like Diagonals/Files/Ranks, or annotated tactical diagrams)
// use those marks, sometimes with no pieces at all. isValidBoardFen rejects
// anything that doesn't parse as a clean 8x8 board rather than risk
// chessground misinterpreting stray punctuation as a corrupted position:
// the plain data-fen text pandoc already rendered into the <code> element is
// left showing instead, exactly as it would with JS disabled entirely.
import { Chessground } from "/vendor/chessground/chessground.min.js";
import { lichessAnalysisUrl } from "/lichess-url.js";

(function () {
  "use strict";

  function isValidBoardFen(fen) {
    var ranks = fen.split("/");
    if (ranks.length !== 8) return false;
    for (var i = 0; i < ranks.length; i++) {
      var count = 0;
      var rank = ranks[i];
      for (var j = 0; j < rank.length; j++) {
        var ch = rank[j];
        if (ch >= "1" && ch <= "8") count += Number(ch);
        else if ("pnbrqkPNBRQK".indexOf(ch) !== -1) count += 1;
        else return false;
      }
      if (count !== 8) return false;
    }
    return true;
  }

  function mount(el) {
    var boardFen = el.getAttribute("data-fen") || "";
    if (!isValidBoardFen(boardFen)) return;

    // Built detached from the document and only swapped in once Chessground
    // has successfully initialized -- if it throws, `el`'s original
    // server-rendered <code>FEN</code> fallback is never touched.
    var boardHost = document.createElement("div");
    boardHost.className = "chess-fen-board";
    Chessground(boardHost, {
      fen: boardFen,
      viewOnly: true,
      coordinates: false,
    });

    var link = document.createElement("a");
    link.className = "chess-fen-link";
    link.href = lichessAnalysisUrl(boardFen);
    link.target = "_blank";
    link.rel = "noopener";
    link.title = "Open this position on Lichess's analysis board";
    link.appendChild(boardHost);

    el.textContent = "";
    el.appendChild(link);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var boards = document.querySelectorAll(".chess-fen");
    for (var i = 0; i < boards.length; i++) {
      try {
        mount(boards[i]);
      } catch (e) {
        if (window.console && console.warn) console.warn("chess-fen: failed to mount board", e);
      }
    }
  });
})();
