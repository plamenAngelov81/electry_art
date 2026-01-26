document.addEventListener("DOMContentLoaded", () => {
    const mainImage = document.getElementById("mainImage");
    const thumbsContainer = document.getElementById("thumbs");

    if (!mainImage || !thumbsContainer) return;

    const thumbs = thumbsContainer.querySelectorAll(".thumb");

    function setActiveThumb(activeImgEl) {
        thumbs.forEach(img => img.classList.remove("thumb-active"));
        activeImgEl.classList.add("thumb-active");
    }

    thumbs.forEach(img => {
        img.addEventListener("click", () => {
            const fullSrc = img.dataset.full || img.src;
            mainImage.src = fullSrc;
            mainImage.alt = img.alt || mainImage.alt;

            setActiveThumb(img);
        });
    });

    if (thumbs.length) setActiveThumb(thumbs[0]);
});

