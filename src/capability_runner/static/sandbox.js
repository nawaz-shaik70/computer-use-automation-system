"use strict";
(() => {
  // This is the target APPLICATION, not the automation. No agent code imports these records.
  const members = {
    "10001": {name:"Maya Carter", balance:"12450.75"},
    "10002": {name:"Daniel Brooks", balance:"807.20"},
    "10003": {name:"Sofia Reynolds", balance:"0.00"}
  };
  let memberId = "";
  const injected = new Set();
  const main = document.querySelector("main");
  function render(title, body) {
    // Titles/body are application-owned templates; user input is never interpolated into HTML.
    main.innerHTML = "<h1>" + title + "</h1><table class='layout'><tr><td>" + body + "</td></tr></table>";
  }
  function navigation(backPath) {
    return '<nav class="actions"><a class="secondary-action" href="' + backPath + '">Back</a><a class="secondary-action" href="/workbench">Search another member</a></nav>';
  }
  function search() {
    render("Member lookup", '<p>Enter a five-digit reviewer test number.</p><form action="/lookup"><table class="field-table"><tr><td>Member number</td><td><input name="member" inputmode="numeric" autocomplete="off" maxlength="5" placeholder="Example: 10001"></td></tr></table><button type="submit">Search</button></form>' +
      '<p class="test-note"><strong>Test numbers:</strong> <code>10001</code>, <code>10002</code>, <code>10003</code> — successful lookups<br><code>90001</code> — permission denied · <code>99999</code> — member not found · <code>00000</code> — validation error</p>' +
      (SANDBOX_SCENARIO === "ambiguous" ? '<button type="button">Search</button>' : ""));
  }
  function savings(loaded = false) {
    if (SANDBOX_SCENARIO === "slow" && !loaded) {
      render("Loading", "<p>Please wait.</p>"); setTimeout(() => savings(true), 650); return;
    }
    if (SANDBOX_SCENARIO === "permission") {render("Permission denied", '<div class="alert"><p>An authorized operator must investigate access rights.</p></div>' + navigation("/accounts")); return;}
    if (!injected.has(SANDBOX_SCENARIO) || SANDBOX_SCENARIO === "outage") {
      if (SANDBOX_SCENARIO === "notice") {render("Maintenance notice", '<form action="/continue"><button>Continue</button></form>'); return;}
      if (["transient","outage"].includes(SANDBOX_SCENARIO)) {
        injected.add(SANDBOX_SCENARIO); render("Service temporarily unavailable", '<form action="/savings"><button>Retry</button></form>'); return;
      }
      if (SANDBOX_SCENARIO === "session") {
        render("Session expired", '<p>This local fixture models operator reauthentication without real credentials.</p><form action="/restore"><button>Restore session</button></form>'); return;
      }
      if (SANDBOX_SCENARIO === "dialog") {
        render("Unexpected confirmation", '<form action="/acknowledge"><button>Acknowledge warning</button></form>');
        window.confirm("Sandbox unexpected confirmation"); return;
      }
    }
    render("Savings account", '<table class="data-table"><tbody><tr><td class="label-cell">Available balance</td><td>' + members[memberId].balance + '</td></tr><tr><td class="label-cell">Currency</td><td>USD</td></tr></tbody></table>' + navigation("/accounts"));
  }
  function navigate(path) {
    if (path === "/workbench") {search(); return;}
    if (!members[memberId]) {render("Session expired", "<p>Return to the entry point.</p>"); return;}
    if (path === "/member") {
      render("Member overview", '<table class="data-table"><tbody><tr><td class="label-cell">Name</td><td>' + members[memberId].name + '</td></tr><tr><td class="label-cell">Identifier</td><td>' + memberId + '</td></tr><tr><td class="label-cell">Email</td><td>synthetic.person@example.invalid</td></tr></tbody></table><div class="actions"><a href="/accounts">View accounts</a></div>' + navigation("/results"));
    } else if (path === "/accounts") {
      render("Member accounts", '<table class="data-table"><thead><tr><th>Account type</th></tr></thead><tbody><tr><td><a class="account-link" href="/savings">Savings</a></td></tr></tbody></table>' + navigation("/member"));
    } else if (path === "/results") {
      render("Search results", '<table class="data-table"><thead><tr><th>Member name</th><th>Action</th></tr></thead><tbody><tr><td>' + members[memberId].name + '</td><td><a class="account-link" href="/member">Open member</a></td></tr></tbody></table>' + navigation("/workbench"));
    } else if (path === "/savings") {savings();}
    else if (path === "/continue") {injected.add("notice"); savings();}
    else if (path === "/restore") {injected.add("session"); savings();}
    else if (path === "/acknowledge") {injected.add("dialog"); savings();}
    else if (path === "/close-account") {
      // Defense in depth: even a policy regression cannot mutate the synthetic account.
      render("Writes disabled", "<p>The read-only sandbox does not implement account closure.</p>");
    }
  }
  document.addEventListener("click", event => {
    const link = event.target.closest("a");
    if (link) {event.preventDefault(); navigate(link.getAttribute("href"));}
  });
  document.addEventListener("submit", event => {
    event.preventDefault(); const form = event.target; const action = form.getAttribute("action");
    if (action === "/lookup") {
      memberId = form.elements.namedItem("member").value;
      if (!/^\d{5}$/.test(memberId) || memberId === "00000") {
        render("Invalid member number", '<p>Enter one of the documented five-digit test values.</p>' + navigation("/workbench"));
      } else if (memberId === "90001") {
        render("Permission denied", '<div class="alert"><p>This synthetic member models an access-control denial. Automation must stop and request human intervention.</p></div>' + navigation("/workbench"));
      } else if (!members[memberId]) {render("No such member", '<p>No synthetic record matched that number.</p>' + navigation("/workbench"));}
      else {navigate("/results");}
    } else {navigate(action);}
  });
  search();
})();
