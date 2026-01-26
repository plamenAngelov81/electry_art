from django import template

register = template.Library()


@register.filter
def youtube_embed(url):
    """
    Converts YouTube link:
    https://www.youtube.com/watch?v=abc123
    to embed version:
    https://www.youtube.com/embed/abc123
    """

    # If it's normal YouTube link
    if "watch?v=" in url:
        return url.replace("watch?v=", "embed/")

    # For shorts videos - youtu.be/ID
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[-1]
        return f"https://www.youtube.com/embed/{video_id}"

    return url
