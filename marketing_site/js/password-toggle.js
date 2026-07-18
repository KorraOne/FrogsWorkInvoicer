/**
 * Accessible show/hide for password inputs.
 * Usage: wrap input + button, or use data-pw-toggle="inputId" on a button.
 */
(function () {
  function setVisible(input, button, visible) {
    input.type = visible ? "text" : "password";
    button.setAttribute("aria-pressed", visible ? "true" : "false");
    button.textContent = visible ? "Hide" : "Show";
    button.setAttribute(
      "aria-label",
      visible ? "Hide password" : "Show password"
    );
  }

  function wire(button) {
    var id = button.getAttribute("data-pw-toggle") || button.getAttribute("aria-controls");
    var input = id ? document.getElementById(id) : null;
    if (!input) return;
    setVisible(input, button, false);
    button.addEventListener("click", function () {
      var show = input.type === "password";
      setVisible(input, button, show);
    });
  }

  document.querySelectorAll("[data-pw-toggle]").forEach(wire);
})();
