#!/bin/bash
for f in *.jpeg; do mv $f `basename $f .jpeg`.jpg; done;
for a in *.jpg; do ffmpeg -i "$a" -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" "${a%.jpg}.jpeg"; done
rm *.jpg
for f in *.jpeg; do mv $f `basename $f .jpeg`.jpg; done;

