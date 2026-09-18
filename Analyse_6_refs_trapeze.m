clear; clc; close all

load('Sim_forme_2.mat')

dx = 5e-3;

indices_reference = [6 12 18 26 32 38];

nombre_references = length(indices_reference);

resolutions = NaN(1, nombre_references);
contrastes = NaN(1, nombre_references);

figure('Color','w','Position',[100 100 1400 750]);

for r = 1:nombre_references

    indice_reference = indices_reference(r);
    signal_reference = double(sensor_data(indice_reference,:));

    coefficients = zeros(1, length(impactXGrid));

    for j = 1:length(impactXGrid)

        signal_compare = double(sensor_data(j,:));

        correlation = xcorr(signal_reference, ...
                            signal_compare, 'coeff');

        coefficients(j) = max(abs(correlation));

    end

    distance_cm = ...
        (impactXGrid-impactXGrid(indice_reference))*dx*100;

    masque_base = abs(distance_cm) > 5;
    ligne_base = mean(coefficients(masque_base));

    contraste = coefficients(indice_reference)/ligne_base;
    contrastes(r) = contraste;

    mi_hauteur = coefficients(indice_reference)/2;

    indice_gauche = find( ...
        coefficients(1:indice_reference) <= mi_hauteur, ...
        1, 'last');

    indice_droit_relatif = find( ...
        coefficients(indice_reference:end) <= mi_hauteur, ...
        1, 'first');

    if ~isempty(indice_gauche) && ...
       ~isempty(indice_droit_relatif)

        indice_droit = ...
            indice_reference + indice_droit_relatif - 1;

        x1 = distance_cm(indice_gauche);
        x2 = distance_cm(indice_gauche+1);

        y1 = coefficients(indice_gauche);
        y2 = coefficients(indice_gauche+1);

        position_gauche = x1 + ...
            (mi_hauteur-y1)*(x2-x1)/(y2-y1);

        x1 = distance_cm(indice_droit-1);
        x2 = distance_cm(indice_droit);

        y1 = coefficients(indice_droit-1);
        y2 = coefficients(indice_droit);

        position_droite = x1 + ...
            (mi_hauteur-y1)*(x2-x1)/(y2-y1);

        resolutions(r) = position_droite-position_gauche;

    end

    subplot(2,3,r)

    plot(distance_cm, coefficients, '-', ...
         'LineWidth', 1.5, ...
         'Color', [0 0.4470 0.7410])

    hold on
    grid on

    yline(mi_hauteur, '--r', ...
          'LineWidth', 1.2);

    yline(ligne_base, '--k', ...
          'LineWidth', 1.2);

    xline(0, ':', ...
          'Color', [0.4 0.4 0.4], ...
          'LineWidth', 1);

    xlabel('Distance [cm]')
    ylabel('Corrélation')

    title(['Référence ', ...
           num2str(indice_reference)])

    ylim([0 1.05])

end

sgtitle('Corrélations pour six positions de référence')

resolution_moyenne = mean(resolutions, 'omitnan');
ecart_resolution = std(resolutions, 'omitnan');

contraste_moyen = mean(contrastes, 'omitnan');
ecart_contraste = std(contrastes, 'omitnan');

fprintf('\nRésultats du trapèze\n')

fprintf('Résolutions individuelles [cm] :\n')
disp(resolutions)

fprintf('Contrastes individuels :\n')
disp(contrastes)

fprintf('Résolution moyenne : %.3f +/- %.3f cm\n', ...
        resolution_moyenne, ...
        ecart_resolution)

fprintf('Contraste moyen : %.3f +/- %.3f\n', ...
        contraste_moyen, ...
        ecart_contraste)