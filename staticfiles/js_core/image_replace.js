// document.addEventListener("DOMContentLoaded", () => {
//     const mainImage = document.getElementById("mainImage");
//     const thumbsContainer = document.getElementById("thumbs");
//
//     if (!mainImage || !thumbsContainer) return;
//
//     const thumbs = thumbsContainer.querySelectorAll(".thumb");
//
//     function setActiveThumb(activeImgEl) {
//         thumbs.forEach(img => img.classList.remove("thumb-active"));
//         activeImgEl.classList.add("thumb-active");
//     }
//
//     thumbs.forEach(img => {
//         img.addEventListener("click", () => {
//             const fullSrc = img.dataset.full || img.src;
//             mainImage.src = fullSrc;
//             mainImage.alt = img.alt || mainImage.alt;
//
//             setActiveThumb(img);
//         });
//     });
//
//     if (thumbs.length) setActiveThumb(thumbs[0]);
// });

document.addEventListener("DOMContentLoaded", () => {
    const mainImage = document.getElementById("mainImage");
    const thumbsContainer = document.getElementById("thumbs");

    if (!mainImage || !thumbsContainer) return;

    const thumbs = Array.from(thumbsContainer.querySelectorAll(".thumb"));
    if (!thumbs.length) return;

    function setActiveThumb(activeImgEl) {
        thumbs.forEach(img => img.classList.remove("thumb-active"));
        activeImgEl.classList.add("thumb-active");
    }

    function setMainImageFromThumb(imgEl) {
        const fullSrc = imgEl.dataset.full || imgEl.getAttribute("src");
        if (!fullSrc) return;

        mainImage.setAttribute("src", fullSrc);
        mainImage.setAttribute("alt", imgEl.getAttribute("alt") || mainImage.getAttribute("alt") || "Product image");
        setActiveThumb(imgEl);
    }

    thumbs.forEach(img => {
        img.addEventListener("click", (e) => {
            setMainImageFromThumb(img);
        });
    });

    setMainImageFromThumb(thumbs[0]);
});