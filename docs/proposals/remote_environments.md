

image building: simplify the "fast launch" / COPY optimizations a bit, 1st-class into the product as creating images
instructions:
    idea for image building: just let you put little "checkpoint" markers in the image -- you can always rebuild from there!
        and you can understand how long it took, how outdated it is, etc
        we recommend that you make these docker file like things in a particular way for latency reasons
    maybe it's like:
        # CACHE-MODE: never
            use this to disable caching entirely
            by convention, use this at the end of your file in order to quickly update to the latest dependencies (make some SYNC line and then update dependencies)
        # CACHE-MODE: file-contents
            default, fancy -- figure out what files were accessed, and if those are changed, regenerate the layer
        # CACHE-MODE: line-text
            simpler mode -- if you change the line, the image will be rebuilt
secrets:
    do those always regenerate it?  I guess so!
env vars:
    regenerates if you change them

one optimization for modal: technically we could return the sandbox that was created when we're making a modal image, would be a little bit faster (would need to change that interface though)
