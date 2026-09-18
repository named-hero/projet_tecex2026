clear all; clc; close all

load('Sim_forme_1.mat')

dx = 5e-3;

% Le cinquieme impact, situe au centre, sert de reference
% indice_reference = ceil(length(impactXGrid)/2); premier : 43/2
indices_reference = [6 12 18 26 32 38];
nombre_references = length(indices_reference);
signal_reference = double(sensor_data(indice_reference,:));

% Tableau qui contiendra les neuf coefficients
coefficients = zeros(1,length(impactXGrid));

for j = 1:length(impactXGrid)

    signal_compare = double(sensor_data(j,:));

    correlation_temporelle = xcorr( ...
        signal_reference, signal_compare, 'coeff');

    coefficients(j) = max(abs(correlation_temporelle));

end

distance_cm = ...
    (impactXGrid-impactXGrid(indice_reference))*dx*100;

figure
plot(distance_cm, coefficients, '-o', 'LineWidth', 1.5)

xlabel('Distance par rapport à l''impact de référence [cm]')
ylabel('Coefficient de corrélation')
title('Corrélation - Rectangle')
grid on
ylim([0 1.05])


%% Calcul du contraste

Cmax = max(coefficients);

% Ligne de base : points situes a plus de 5 cm du pic principal
points_fond = abs(distance_cm) > 5;
ligne_base = mean(coefficients(points_fond));

contraste = Cmax/ligne_base;


%% Calcul de la resolution a mi-hauteur

mi_hauteur = Cmax/2;

% Dernier point sous la mi-hauteur a gauche du pic
indice_gauche = find( ...
    coefficients(1:indice_reference) < mi_hauteur, ...
    1, 'last');

% Premier point sous la mi-hauteur a droite du pic
indice_droite_relatif = find( ...
    coefficients(indice_reference:end) < mi_hauteur, ...
    1, 'first');

indice_droite = indice_reference + indice_droite_relatif - 1;

% Interpolation pour trouver plus precisement les croisements
x_gauche = interp1( ...
    coefficients([indice_gauche, indice_gauche+1]), ...
    distance_cm([indice_gauche, indice_gauche+1]), ...
    mi_hauteur);

x_droite = interp1( ...
    coefficients([indice_droite-1, indice_droite]), ...
    distance_cm([indice_droite-1, indice_droite]), ...
    mi_hauteur);

resolution = x_droite-x_gauche;


%% Affichage des resultats

fprintf('Ligne de base : %.3f\n', ligne_base)
fprintf('Contraste : %.3f\n', contraste)
fprintf('Resolution : %.3f cm\n', resolution)

hold on
yline(ligne_base, '--k', 'Ligne de base')
yline(mi_hauteur, '--r', 'Mi-hauteur')
xline(x_gauche, ':r')
xline(x_droite, ':r')
hold off