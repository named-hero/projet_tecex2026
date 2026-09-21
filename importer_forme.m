clear

%% Choisir un fichier
[file, folder] = uigetfile('*.png');
file_location = string(folder) + string(file);
pixels = imread(file_location);

%% Crop image pour cadrer parfaitement la forme
%Identification de tout les points blanc
if ndims(pixels) == 3
    mask = any(pixels == 255, 3);
else
    mask = pixels == 255;
end

[rowIdx, colIdx] = find(mask);

if isempty(rowIdx)
    error("No object found in the image.");
end

% Sélection des bordure de la forme
topRow = min(rowIdx);
bottomRow = max(rowIdx);
leftCol = min(colIdx);
rightCol = max(colIdx);

%Crop de l'image
croppedPixels = pixels(topRow:bottomRow, leftCol:rightCol, :);

imshow(croppedPixels) % Permet de visulaliser l'image

%% Dernières actions et enregistrement
croppedPixels(croppedPixels > 0) = 1; % Remplacer pixels non noir par valeur 1

shape = croppedPixels;
nom = inputdlg("Quelle est le nom de la forme");

%Enregistrer le fichier image initial pour backlog
copyfile(file_location, append("projet_tecex2026\Formes (png)\", nom, ".png"))
%Enregistrer nouveau fichier dans variable <shape>
save(append("projet_tecex2026\Formes enregistrer\", nom), "shape")
