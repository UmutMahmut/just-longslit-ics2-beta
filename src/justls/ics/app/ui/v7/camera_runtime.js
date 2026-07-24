(function () {
  "use strict";

  const selector = 'img[src^="/camera/"]';

  function refreshCameraImages() {
    const stamp = Date.now().toString();
    document.querySelectorAll(selector).forEach((image) => {
      const base = image.dataset.icsCameraSrc || image.getAttribute("src").split("?")[0];
      image.dataset.icsCameraSrc = base;
      image.src = `${base}?frame=${stamp}`;
      image.style.display = "";
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    refreshCameraImages();
    window.setInterval(refreshCameraImages, 1500);
  });
})();
