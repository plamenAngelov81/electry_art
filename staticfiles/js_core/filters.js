document.addEventListener("DOMContentLoaded", function () {
    const form = document.querySelector(".js-auto-submit");
    if (!form) return;

    const autoFields = form.querySelectorAll(
        'select, input[type="checkbox"]'
    );

    autoFields.forEach(field => {
        field.addEventListener("change", () => {
            form.submit();
        });
    });
});
