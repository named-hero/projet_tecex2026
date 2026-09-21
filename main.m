%% Installation
% Ajouter k-Wave au chemin MATLAB avant de lancer ce script.
%Commentaire  test synchroniastion 
%% Initialisation variables
clear; clc; close all

%Tableau des formes
formes_custom_plaques = {
    "Formes enregistrer\eye.mat","Formes enregistrer\peinture-v1"
};
formes_basique = {'Cercle','Rectangle','Trapeze trou et deux coupes', 'Forme en D'};
impacts_formes_basique = {
    [46 19; 46 30; 46 41;
    62 19; 62 30; 62 41;
    78 19; 78 30; 78 41];

    [20 18; 20 30; 20 42;
    62 18; 62 30; 62 42;
    104 18; 104 30; 104 42];

    [29 15; 29 27; 29 39;
    62 15; 62 27; 62 39;
    95 15; 95 27; 95 39];

    [39 17; 39 29; 39 40;
    58 17; 58 29; 58 40;
    95 17; 95 29; 95 40];
    };

% Points d'impact pour peinture et piano
%case 5
%    lignes_impacts = [31 62 93]; colonnes_impacts = [14 28 40];
%case 6
%    lignes_impacts = [24 61 105]; colonnes_impacts = [15 25 35];


%Acier TODO Mettre les bonnnes propriétés
materiaux(1)=struct( ...
    'sound_speed', 3000,  ...
    'density', 2500);
%Aluminium TODO Mettre les bonnnes propriétés
materiaux(2)=struct( ...
    'sound_speed', 3000,  ...
    'density', 2500);
%Plastique TODO Mettre les bonnnes propriétés
materiaux(3)=struct( ...
    'sound_speed', 3000,  ...
    'density', 2500);

% basique : Fait référence au forme personnalisé
% index : L'index dans le tableau
formes_a_tester(1) = struct('index', 3, 'basique', true);
materiau = materiaux(1);

calcul_simulation = false;  % Compute simulation
analyse_simulation = false; % Compute analyse

%% Simulation grid parameter
Nx = 124;
Ny = 60;
dx = 5e-3;
dy = 5e-3;
kgrid = kWaveGrid(Nx,dx,Ny,dy);
airSpeed = 330;
airDensity = 10;

function rectangle = Rectangle(width, height)
    rectangle.i_min = 4; rectangle.i_max = 4 + width;
    rectangle.j_min = 4; rectangle.j_max = 4 + height;
end

function cercle = Cercle(x, y, rayon)
    cercle.centre_i = x; 
    cercle.centre_j = y; 
    cercle.rayon = rayon;
end

% Seulement pour les test, pas vraiment utiliser
function trapeze = Trapeze()
    trapeze.inclinaison = 0.10;  % Plus grand = bord droit plus oblique.
    trapeze.i_min = 4; trapeze.i_max = 120;
    trapeze.j_min = 4; trapeze.j_max = 56;
    trapeze.coupe_1_i = 24; trapeze.coupe_1_j = 12;
    trapeze.coupe_2_i = 18; trapeze.coupe_2_j = 8;
    trapeze.trou_i = 108; trapeze.trou_j = 18; trapeze.rayon_trou = 4;
    % rayon_trou = 0 supprime le trou du trapeze.
end

% TODO Refaire la forme en custom
function palette = Palette_Couleur()
    palette.centre_i = 62; palette.centre_j = 30;
    palette.rayon_i = 58; palette.rayon_j = 26;
    palette.trou_i = 25; palette.trou_j = 40;
    palette.trou_rayon_i = 5; palette.trou_rayon_j = 4;
    palette.encoche_i = 75; palette.encoche_j = 54;
    palette.encoche_rayon_i = 15; palette.encoche_rayon_j = 12;
    % Augmenter encoche_rayon_j creuse davantage le bord droit
end

%TODO Réimplémenter pour contrôler 
function forme_D = D_shape(x)
    forme_D.centre_i = x; forme_D.rayon_i = 58; 
    forme_D.bord_plat_j = 4; forme_D.rayon_arrondi_j = 52;
end

%TODO Refaire la forme en custom
function piano = Piano()
    piano.haut_i = 4; piano.bas_i = 120;
    piano.bord_gauche_j = 4; piano.largeur_haute_j = 46;
    piano.hauteur_voute_i = 21;  % Taille de l'arrondi en haut.
    piano.elargissement_bas_j = 10;  % Largeur gagnee vers le bas.
    piano.epaule_i = 70;  % Position de l'elargissement vertical.
    piano.douceur_epaule_i = 5;  % Plus grand = courbe plus progressive.
end

function medium = customShape(medium, pixels_map, largeur_cible, materiau)    
    if ~islogical(pixels_map)
        pixels_map = pixels_map ~= 0;
    end
    
    [r, c] = find(pixels_map);
    if isempty(r)
        error('La forme personnalisée est vide.');
    end
    
    pixels_map = pixels_map(min(r):max(r), min(c):max(c));
    
    largeur_source = size(pixels_map, 2);
    echelle = largeur_cible / largeur_source;
    masque = imresize(pixels_map, echelle, 'nearest') > 0;
    
    [NxLocal, NyLocal] = size(medium.sound_speed);
    [h, w] = size(masque);
    
    i0 = round((NxLocal - h) / 2) + 1;
    j0 = round((NyLocal - w) / 2) + 1;
    i1 = i0 + h - 1;
    j1 = j0 + w - 1;
    
    if i0 < 1 || j0 < 1 || i1 > NxLocal || j1 > NyLocal
        error('La forme redimensionnée dépasse la grille.');
    end
    
    mask = false(NxLocal, NyLocal);
    mask(i0:i1, j0:j1) = masque;
    
    medium.sound_speed(mask) = materiau.sound_speed;
    medium.density(mask) = materiau.density;
end


%% Boucle de simulation
for forme = formes_a_tester
    if forme.basique
        nom_forme = formes_basique{forme.index};
    else
        [~, name, ~] = fileparts(pathStr);
        nom_forme = name;
    end
    %% Shape of the medium
    medium.sound_speed = airSpeed * ones(Nx,Ny);
    medium.density = airDensity * ones(Nx,Ny);
    medium.alpha_coeff = 0.75;
    medium.alpha_power = 1.5;
    [I,J] = ndgrid(1:Nx,1:Ny);

    % Tous les contours restent a l'interieur de la bordure d'air.
    bordure = I >= 4 & I <= 120 & J >= 4 & J <= 56;

    if forme.basique
        %% Choix de la geometrie
        switch forme.index
            case 1  % Cercle : rayon maximal compatible avec la largeur initiale
                cercle = Cercle(Nx/2, Ny/2, 26);
                matiere = (I-cercle.centre_i).^2 + (J-cercle.centre_j).^2 ...
                    <= cercle.rayon^2;
            case 2  % Rectangle
                rect = Rectangle(116, 52);
                matiere = I>=rect.i_min & I<=rect.i_max ...
                    & J>=rect.j_min & J<=rect.j_max;
            case 3  % Trapeze avec trou et deux coupes
                trapeze = Trapeze();
                bord_incline = trapeze.j_max - ...
                    round(trapeze.inclinaison*(I-trapeze.i_min));
                coupe_1 = (I-trapeze.i_min)/trapeze.coupe_1_i ...
                    + (J-trapeze.j_min)/trapeze.coupe_1_j <= 1;
                coupe_2 = (trapeze.i_max-I)/trapeze.coupe_2_i ...
                    + (J-trapeze.j_min)/trapeze.coupe_2_j <= 1;
                trou = trapeze.rayon_trou>0 & ...
                    (I-trapeze.trou_i).^2 + (J-trapeze.trou_j).^2 ...
                    <= trapeze.rayon_trou^2;
                matiere = I>=trapeze.i_min & I<=trapeze.i_max ...
                    & J>=trapeze.j_min & J<=bord_incline ...
                    & ~coupe_1 & ~coupe_2 & ~trou;
            case 4  % Palette de peintre : trou en haut, encoche arrondie profonde
                palette = Palette_Couleur();
                ovale = ((I-palette.centre_i)/palette.rayon_i).^2 ...
                    + ((J-palette.centre_j)/palette.rayon_j).^2 <= 1;
                trou_pouce = ((I-palette.trou_i)/palette.trou_rayon_i).^2 ...
                    + ((J-palette.trou_j)/palette.trou_rayon_j).^2 <= 1;
                encoche = ((I-palette.encoche_i)/palette.encoche_rayon_i).^2 ...
                    + ((J-palette.encoche_j)/palette.encoche_rayon_j).^2 <= 1;
                matiere = ovale & ~trou_pouce & ~encoche;
            case 5  % D : cote plat a gauche, cote bombe a droite
                forme_D = D_shape(Nx/2);
                matiere = J>=forme_D.bord_plat_j ...
                    & ((I-forme_D.centre_i)/forme_D.rayon_i).^2 ...
                    + ((J-forme_D.bord_plat_j)/forme_D.rayon_arrondi_j).^2 <= 1;
            case 6  % Piano a queue : voute ronde, cote gauche et clavier droits
                piano = Piano();
                jonction_i = piano.haut_i + piano.hauteur_voute_i;
                centre_voute_j = (piano.bord_gauche_j+piano.largeur_haute_j)/2;
                rayon_voute_j = (piano.largeur_haute_j-piano.bord_gauche_j)/2;
                voute = I<=jonction_i & ...
                    ((I-jonction_i)/piano.hauteur_voute_i).^2 ...
                    + ((J-centre_voute_j)/rayon_voute_j).^2 <= 1;
                bord_droit = piano.largeur_haute_j ...
                    + piano.elargissement_bas_j./ ...
                    (1+exp(-(I-piano.epaule_i)/piano.douceur_epaule_i));
                corps = I>jonction_i & I<=piano.bas_i ...
                    & J>=piano.bord_gauche_j & J<=bord_droit;
                matiere = voute | corps;
        end
        matiere = matiere & bordure; % Matière est tout les pixels que l'on va changer propriétés
        medium.sound_speed(matiere) = materiau.sound_speed;
        medium.density(matiere) = materiau.density;

        %% Define sensor
        % Neuf positions physiques d'impact : 3 lignes x 3 colonnes.
        % La grille suit la partie utile de chaque forme; les comparaisons
        % entre formes concernent donc leur surface utilisable respective.
        % Maillage dense AUXILIAIRE pour mesurer la largeur autour de chacune.
        impacts = impacts_formes_basique{forme.index};

    else
        obj = load(formes_custom_plaques(forme.index));
        medium = customShape(medium, obj.shape, Nx, materiau);
        impacts = obj.impacts; %TODO Donne une erreur pour l'instant. Il faut ajouter les impacts d'une manière ou d'une autre

    end
    pas_profil = -6:6;  % 0,5 cm par pas, de -3 a +3 cm.
    sondes = impacts;
    for p = 1:size(impacts, 1)
        pas_profil_impact = pas_profil;
        % Sur le cercle, les impacts 4 et 6 ont besoin d'un profil plus long
        % selon x pour chercher les deux passages a mi-hauteur.
        % A j = 30, les points supplementaires restent dans le cercle.
        if forme.index == 1 && (p == 4 || p == 6)
            pas_profil_impact = -10:10;  % +/- 5 cm, tous les 0,5 cm.
        end
        sondes = [sondes; ...
            [impacts(p,1)+pas_profil_impact(:), repmat(impacts(p,2),numel(pas_profil_impact),1)]; ...
            [repmat(impacts(p,1),numel(pas_profil_impact),1), impacts(p,2)+pas_profil_impact(:)]]; %#ok<AGROW>
    end
    sondes = unique(sondes,'rows');
    %Détection sondes hors bornes ou dans l'air
    if any(sondes(:,1)<1| sondes(:,2)<1 | sondes(:,1)>Nx | sondes(:,2)>Ny) ...
            || any(~matiere(sub2ind([Nx Ny],sondes(:,1),sondes(:,2))))
        error('Forme %s : un impact ou une sonde auxiliaire est dans l''air.',nom_forme)
    end
    % Identifies sur la carte la position des sondes
    sensor.mask = false(Nx,Ny);
    sensor.mask(sub2ind([Nx Ny],sondes(:,1),sondes(:,2))) = true;
    [sensorI,sensorJ] = ind2sub([Nx Ny],find(sensor.mask));
    positions_sondes = [sensorI sensorJ];  % Ordre des lignes de sensor_data.
    [ok, ~] = ismember(impacts,positions_sondes,'rows');
    assert(all(ok),'Impossible d''associer les 9 impacts aux signaux.')

    %% Source definition
    % Un seul émetteur fixe. Les 9 points sont les emplacements testes.
    % TODO Implémenter l'ajout de plusieurs sources différentes
    % TODO Cette position n'est peut-être pas valide si forme personnalisé
    source_pos_x = 62;
    source_pos_y = 9;
    source_radius = 2;
    source_magnitude = 10;
    source.p0 = source_magnitude * makeDisc(Nx,Ny, ...
        source_pos_x,source_pos_y,source_radius);
    if any(~matiere(source.p0>0))
        error('Forme %s : le disque de la source touche l''air.',nom_forme)
    end

    %% Visualisation de la grille de simulation
    figure('Name',nom_forme,'Color','w');
    imagesc(kgrid.y_vec*1e3,kgrid.x_vec*1e3,medium.sound_speed)
    axis image; colorbar; hold on
    h1 = plot(kgrid.y_vec(impacts(:,2))*1e3, ...
        kgrid.x_vec(impacts(:,1))*1e3,'b+','MarkerSize',10,'LineWidth',1.3);
    h2 = plot(kgrid.y_vec(source_pos_y)*1e3, ...
        kgrid.x_vec(source_pos_x)*1e3,'ro','MarkerFaceColor','r');
    for p = 1:9
        text(kgrid.y_vec(impacts(p,2))*1e3+4, ...
            kgrid.x_vec(impacts(p,1))*1e3,num2str(p),'Color','k');
    end
    
    title(nom_forme)
    xlabel('Position y [mm]'); ylabel('Position x [mm]')
    legend([h1 h2],{'Impacts 1 a 9','Émetteur fixe'},'Location','best')
    drawnow
    if ~calcul_simulation
        fprintf('Forme %s : geometrie affichée; simulation ignorée.\n',nom_forme)
        continue
    end

    %% Simulation
    fprintf('Simulation %s (%d sondes virtuelles)\n', ...
        nom_forme,size(positions_sondes,1))
    sensor_data = kspaceFirstOrder2D(kgrid,medium,source,sensor, ...
        'PMLSize',2,'PMLInside',false,'DataCast','single','PlotSim',false);

    %% Sauvegarde des donnees
    nom_fichier = sprintf('Sim_9_impacts_forme_%d.mat',nom_forme);
    save(nom_fichier,'sensor_data','positions_sondes','impacts', ...
        'indices_impacts','dx','dy','materiau','forme','formes_basique', ...
        'cercle','rectangle','trapeze','palette','forme_D','piano')
    fprintf('Enregistre : %s\n',nom_fichier)
end
