clear
pixels = imread("projet_tecex2026\Formes (png)\Forme test.png");

if ndims(pixels) == 3
    mask = any(pixels == 255, 3);   % for a white background
else
    mask = pixels == 255;
end

[rowIdx, colIdx] = find(mask);

if isempty(rowIdx)
    error("No object found in the image.");
end

topRow = min(rowIdx);
bottomRow = max(rowIdx);
leftCol = min(colIdx);
rightCol = max(colIdx);

croppedPixels = pixels(topRow:bottomRow, leftCol:rightCol, :);

imshow(croppedPixels)

croppedPixels(croppedPixels > 0) = 1;
shape = croppedPixels;
nom = inputdlg("Quelle est le nom de la forme");
save(append("projet_tecex2026\Formes enregistrer\", nom), "shape")
