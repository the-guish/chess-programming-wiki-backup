// Client-side title search. No framework, no build step, no server: fetches
// /search-index.json (an array of [title, path] pairs, one per wiki page)
// once on first use and filters it in the browser as the reader types.
(function () {
  "use strict";

  var indexPromise = null;

  function loadIndex() {
    if (!indexPromise) {
      indexPromise = fetch("/search-index.json").then(function (r) {
        return r.json();
      });
    }
    return indexPromise;
  }

  function escapeHtml(s) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Wires one search input to one results container. `render` receives the
  // matches (already capped) and owns turning them into markup, so the
  // compact header dropdown and the full-page search list can each render
  // differently from the same matching logic.
  function attach(input, results, render, maxResults) {
    if (!input || !results) return;

    input.addEventListener("input", function () {
      var query = input.value.trim().toLowerCase();
      if (query.length === 0) {
        results.innerHTML = "";
        results.classList.add("hidden");
        return;
      }
      loadIndex().then(function (pages) {
        var matches = [];
        for (var i = 0; i < pages.length && matches.length < maxResults; i++) {
          var title = pages[i][0];
          if (title.toLowerCase().indexOf(query) !== -1) {
            matches.push(pages[i]);
          }
        }
        render(matches, query);
      });
    });

    document.addEventListener("click", function (e) {
      if (e.target !== input) {
        results.classList.add("hidden");
      }
    });
    input.addEventListener("focus", function () {
      if (results.innerHTML !== "") results.classList.remove("hidden");
    });
  }

  function renderDropdown(results) {
    return function (matches) {
      if (matches.length === 0) {
        results.innerHTML = '<p class="p-2 text-slate-500">No matches</p>';
      } else {
        results.innerHTML = matches
          .map(function (m) {
            return (
              '<a class="block px-2 py-1 hover:bg-slate-100" href="/' +
              m[1] +
              '">' +
              escapeHtml(m[0]) +
              "</a>"
            );
          })
          .join("");
      }
      results.classList.remove("hidden");
    };
  }

  function renderList(results) {
    return function (matches) {
      results.innerHTML = matches
        .map(function (m) {
          return (
            '<li><a href="/' + m[1] + '">' + escapeHtml(m[0]) + "</a></li>"
          );
        })
        .join("");
    };
  }

  // "Random page": the sub-nav link's plain href (Special:AllPages) is the
  // no-JS fallback — a reasonable landing page, not a dead end — so this
  // only has to upgrade the click when JS runs. Reuses the same
  // search-index.json fetch `attach` already loads on demand, rather than
  // shipping a second copy of the page list.
  function wireRandomPage(link) {
    if (!link) return;
    link.addEventListener("click", function (e) {
      e.preventDefault();
      loadIndex().then(function (pages) {
        if (pages.length === 0) return;
        var pick = pages[Math.floor(Math.random() * pages.length)];
        window.location.href = "/" + pick[1];
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var headerInput = document.getElementById("search-input");
    var headerResults = document.getElementById("search-results");
    attach(headerInput, headerResults, renderDropdown(headerResults), 20);

    var pageInput = document.getElementById("search-page-input");
    var pageResults = document.getElementById("search-page-results");
    attach(pageInput, pageResults, renderList(pageResults), 200);

    wireRandomPage(document.getElementById("random-page-link"));
  });
})();
