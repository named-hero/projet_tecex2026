function Analyser_simulation(fichiers, dossier)
% ANALYSER_SIMULATIONS Analyse une ou plusieurs simulations.
%
% Utilisation :
%   analyser_simulations()
%       -> ouvre une fenêtre pour choisir les fichiers.
%
%   analyser_simulations(fichier)
%       -> analyse le fichier fourni.
%
%   analyser_simulations({fichier1, fichier2}, dossier)
%       -> analyse plusieurs fichiers.
%
% Le fichier resolution_contraste.m doit être accessible dans le chemin MATLAB.

    %% Configuration
    methode = 'absolue'; % Seuil 0.5. 'fond' : autre convention.

    % S'assurer que resolution_contraste.m est accessible
    dossier_code = fileparts(mfilename('fullpath'));
    addpath(dossier_code);

    %% Si aucun fichier n'est fourni, ouvrir le sélecteur
    if nargin < 1 || isempty(fichiers)

        [fichiers, dossier] = uigetfile( ...
            '*.mat', ...
            'Choisir les fichiers de SIMULATION', ...
            'MultiSelect', 'on');

        if isequal(fichiers, 0)
            disp('Analyse annulée.');
            return;
        end
    end

    %% Normaliser les entrées
    if ischar(fichiers) || isstring(fichiers)
        fichiers = cellstr(fichiers);
    end

    % Si le dossier n'a pas été fourni, utiliser le dossier du premier fichier
    if nargin < 2 || isempty(dossier)
        [dossier, ~, ~] = fileparts(fichiers{1});

        % Si fichiers contient seulement un nom de fichier
        if isempty(dossier)
            dossier = pwd;
        end
    end

    %% Créer le dossier de sortie
    sortie = fullfile(dossier, 'analyses');

    if ~isfolder(sortie)
        mkdir(sortie);
    end

    %% Nombre de chiffres significatifs
    nSignificatif = 4;
    fmt = ['%.' num2str(nSignificatif) 'g'];

    %% Analyse de chaque fichier
    for k = 1:numel(fichiers)

        chemin = fullfile(dossier, fichiers{k});

        fprintf('\nAnalyse de : %s\n', chemin);

        %% Lire les informations du fichier
        info_forme = load(chemin);

        nom = info_forme.nom_forme;
        date = info_forme.date;
        materiau = info_forme.materiau;

        %% Calcul de la résolution / contraste
        stats = resolution_contraste(chemin, methode);

        %% Nom de base des fichiers de sortie
        base = fullfile(sortie, ...
            ['Analyse_' nom '_' methode]);

        %% Sauvegarder les résultats
        save([base '.mat'], 'stats');

        writetable(stats.par_impact, ...
            [base '_impacts.csv']);

        writetable(stats.resume, ...
            [base '_resume.csv']);

        %% Créer la ligne du résumé général
        resume = stats.resume;

        T = table( ...
            date, ...
            string(nom), ...
            string(sprintf(fmt, resume.Moyenne(1))), ...
            string(sprintf([fmt ' – ' fmt], ...
                resume.Minimum(1), resume.Maximum(1))), ...
            string(sprintf(fmt, resume.Ecart_type(1))), ...
            string(sprintf(fmt, resume.Moyenne(2))), ...
            string(sprintf([fmt ' – ' fmt], ...
                resume.Minimum(2), resume.Maximum(2))), ...
            string(sprintf(fmt, resume.Ecart_type(2))), ...
            string(sprintf(fmt, resume.Moyenne(3))), ...
            string(sprintf([fmt ' – ' fmt], ...
                resume.Minimum(3), resume.Maximum(3))), ...
            string(sprintf(fmt, resume.Ecart_type(3))), ...
            resume.N_total(1), ...
            materiau.nom_materiau, ...
            'VariableNames', { ...
                'Date', ...
                'Nom', ...
                'Rx moy.', ...
                'Rx Min/Max', ...
                'Rx_Ecart_type', ...
                'Ry moy.', ...
                'Ry Min/Max', ...
                'Ry_Ecart_type', ...
                'Contraste moy.', ...
                'Contraste Min/Max', ...
                'Contraste_Ecart_type', ...
                'Nb_senseurs', ...
                'Matériau'});

        %% Ajouter au résumé général
        fichier_resume = fullfile(sortie, 'Résumer.csv');

        if isfile(fichier_resume)
            writetable(T, fichier_resume, ...
                'WriteMode', 'append', ...
                'WriteVariableNames', false);
        else
            writetable(T, fichier_resume);
        end

        fprintf('Analyse enregistrée : %s.mat\n', base);
    end
end
