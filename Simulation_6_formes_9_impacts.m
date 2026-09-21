%% Installation
% Ajouter k-Wave au chemin MATLAB avant de lancer ce script.

%% Clear
clear; clc; close all

formes_a_tester = 1:6;  % 1=cercle, 2=rectangle, 3=trapeze, 4=palette, 5=D, 6=piano.
seulement_geometrie = false;  % true = voir les formes sans calcul k-Wave.
noms_formes = {'Cercle','Rectangle','Trapeze trou et deux coupes', ...
    'Palette de peintre','Forme en D','Contour de piano'};

%% Reglages des formes (dimensions en points de grille : 1 point = 5 mm)
% i augmente vers le bas des figures; j augmente vers la droite.
% Changer une valeur ici, puis relancer seulement la forme concernee.
cercle.centre_i = 62; cercle.centre_j = 30; cercle.rayon = 26;

rectangle.i_min = 4; rectangle.i_max = 120;
rectangle.j_min = 4; rectangle.j_max = 56;

trapeze.inclinaison = 0.10;  % Plus grand = bord droit plus oblique.
trapeze.i_min = 4; trapeze.i_max = 120;
trapeze.j_min = 4; trapeze.j_max = 56;
trapeze.coupe_1_i = 24; trapeze.coupe_1_j = 12;
trapeze.coupe_2_i = 18; trapeze.coupe_2_j = 8;
trapeze.trou_i = 108; trapeze.trou_j = 18; trapeze.rayon_trou = 4;
% rayon_trou = 0 supprime le trou du trapeze.

palette.centre_i = 62; palette.centre_j = 30;
palette.rayon_i = 58; palette.rayon_j = 26;
palette.trou_i = 25; palette.trou_j = 40;
palette.trou_rayon_i = 5; palette.trou_rayon_j = 4;
palette.encoche_i = 75; palette.encoche_j = 54;
palette.encoche_rayon_i = 15; palette.encoche_rayon_j = 12;
% Augmenter encoche_rayon_j creuse davantage le bord droit.

forme_D.centre_i = 62; forme_D.rayon_i = 58;
forme_D.bord_plat_j = 4; forme_D.rayon_arrondi_j = 52;

piano.haut_i = 4; piano.bas_i = 120;
piano.bord_gauche_j = 4; piano.largeur_haute_j = 46;
piano.hauteur_voute_i = 21;  % Taille de l'arrondi en haut.
piano.elargissement_bas_j = 10;  % Largeur gagnee vers le bas.
piano.epaule_i = 70;  % Position de l'elargissement vertical.
piano.douceur_epaule_i = 5;  % Plus grand = courbe plus progressive.

%% Simulation grid parameter
Nx = 124;
Ny = 60;
dx = 5e-3;
dy = 5e-3;
kgrid = kWaveGrid(Nx,dx,Ny,dy);
SoundSpeed = 3000;  % Parametres provisoires communs aux six formes
Density = 2500;
airSpeed = 330;
airDensity = 10;

%% Changement du pas de temps
% Laisser k-Wave le fixer automatiquement.

for forme = formes_a_tester

    %% Shape of the medium
    medium.sound_speed = airSpeed * ones(Nx,Ny);
    medium.density = airDensity * ones(Nx,Ny);
    medium.alpha_coeff = 0.75;
    medium.alpha_power = 1.5;
    [I,J] = ndgrid(1:Nx,1:Ny);

    % Tous les contours restent a l'interieur de la bordure d'air.
    bordure = I >= 4 & I <= 120 & J >= 4 & J <= 56;

    %% Choix de la geometrie
    switch forme
        case 1  % Cercle : rayon maximal compatible avec la largeur initiale
            matiere = (I-cercle.centre_i).^2 + (J-cercle.centre_j).^2 ...
                <= cercle.rayon^2;
        case 2  % Rectangle
            matiere = I>=rectangle.i_min & I<=rectangle.i_max ...
                & J>=rectangle.j_min & J<=rectangle.j_max;
        case 3  % Trapeze avec trou et deux coupes
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
            ovale = ((I-palette.centre_i)/palette.rayon_i).^2 ...
                + ((J-palette.centre_j)/palette.rayon_j).^2 <= 1;
            trou_pouce = ((I-palette.trou_i)/palette.trou_rayon_i).^2 ...
                + ((J-palette.trou_j)/palette.trou_rayon_j).^2 <= 1;
            encoche = ((I-palette.encoche_i)/palette.encoche_rayon_i).^2 ...
                + ((J-palette.encoche_j)/palette.encoche_rayon_j).^2 <= 1;
            matiere = ovale & ~trou_pouce & ~encoche;
        case 5  % D : cote plat a gauche, cote bombe a droite
            matiere = J>=forme_D.bord_plat_j ...
                & ((I-forme_D.centre_i)/forme_D.rayon_i).^2 ...
                + ((J-forme_D.bord_plat_j)/forme_D.rayon_arrondi_j).^2 <= 1;
        case 6  % Piano a queue : voute ronde, cote gauche et clavier droits
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
    matiere = matiere & bordure;
    medium.sound_speed(matiere) = SoundSpeed;
    medium.density(matiere) = Density;

    %% Define sensor
    % Neuf positions physiques d'impact : 3 lignes x 3 colonnes.
    % La grille suit la partie utile de chaque forme; les comparaisons
    % entre formes concernent donc leur surface utilisable respective.
    % Maillage dense AUXILIAIRE pour mesurer la largeur autour de chacune.
    switch forme
        case 1
            lignes_impacts = [46 62 78]; colonnes_impacts = [19 30 41];
        case 2
            lignes_impacts = [20 62 104]; colonnes_impacts = [18 30 42];
        case 3
            lignes_impacts = [29 62 95]; colonnes_impacts = [15 27 39];
        case 4
            lignes_impacts = [39 58 95]; colonnes_impacts = [17 29 40];
        case 5
            lignes_impacts = [31 62 93]; colonnes_impacts = [14 28 40];
        case 6
            lignes_impacts = [24 61 105]; colonnes_impacts = [15 25 35];
    end
    [IG,JG] = ndgrid(lignes_impacts,colonnes_impacts);
    impacts = [IG(:) JG(:)];
    pas_profil = -6:6;  % 0,5 cm par pas, de -3 a +3 cm.
    sondes = impacts;
    for p = 1:9
        pas_profil_impact = pas_profil;
        % Sur le cercle, les impacts 4 et 6 ont besoin d'un profil plus long
        % selon x pour chercher les deux passages a mi-hauteur.
        % A j = 30, les points supplementaires restent dans le cercle.
        if forme == 1 && (p == 4 || p == 6)
            pas_profil_impact = -10:10;  % +/- 5 cm, tous les 0,5 cm.
        end
        sondes = [sondes; ...
            [impacts(p,1)+pas_profil_impact(:), repmat(impacts(p,2),numel(pas_profil_impact),1)]; ...
            [repmat(impacts(p,1),numel(pas_profil_impact),1), impacts(p,2)+pas_profil_impact(:)]]; %#ok<AGROW>
    end
    sondes = unique(sondes,'rows');
    if any(sondes(:,1)<1 | sondes(:,1)>Nx | sondes(:,2)<1 | sondes(:,2)>Ny) ...
            || any(~matiere(sub2ind([Nx Ny],sondes(:,1),sondes(:,2))))
        error('Forme %d : un impact ou une sonde auxiliaire est dans l''air.',forme)
    end
    sensor.mask = false(Nx,Ny);
    sensor.mask(sub2ind([Nx Ny],sondes(:,1),sondes(:,2))) = true;
    [sensorI,sensorJ] = ind2sub([Nx Ny],find(sensor.mask));
    positions_sondes = [sensorI sensorJ];  % Ordre des lignes de sensor_data.
    [ok,indices_impacts] = ismember(impacts,positions_sondes,'rows');
    assert(all(ok),'Impossible d''associer les 9 impacts aux signaux.')

    %% Source definition
    % Un seul emetteur fixe. Les 9 points sont les emplacements testes.
    sourceGrid = [62 9];
    source_radius = 2;
    source_magnitude = 10;
    source.p0 = source_magnitude * makeDisc(Nx,Ny, ...
        sourceGrid(1),sourceGrid(2),source_radius);
    if any(~matiere(source.p0>0))
        error('Forme %d : le disque de la source touche l''air.',forme)
    end

    %% Visualisation de la grille de simulation
    figure('Name',noms_formes{forme},'Color','w');
    imagesc(kgrid.y_vec*1e3,kgrid.x_vec*1e3,medium.sound_speed)
    axis image; colorbar; hold on
    h1 = plot(kgrid.y_vec(impacts(:,2))*1e3, ...
        kgrid.x_vec(impacts(:,1))*1e3,'b+','MarkerSize',10,'LineWidth',1.3);
    h2 = plot(kgrid.y_vec(sourceGrid(2))*1e3, ...
        kgrid.x_vec(sourceGrid(1))*1e3,'ro','MarkerFaceColor','r');
    for p = 1:9
        text(kgrid.y_vec(impacts(p,2))*1e3+4, ...
            kgrid.x_vec(impacts(p,1))*1e3,num2str(p),'Color','k');
    end
    title(noms_formes{forme})
    xlabel('Position y [mm]'); ylabel('Position x [mm]')
    legend([h1 h2],{'Impacts 1 a 9','Emetteur fixe'},'Location','best')
    drawnow
    if seulement_geometrie
        fprintf('Forme %d : geometrie affichee; simulation ignoree.\n',forme)
        continue
    end

    %% Simulation
    fprintf('Simulation %d/6 : %s (%d sondes virtuelles)\n', ...
        forme,noms_formes{forme},size(positions_sondes,1))
    sensor_data = kspaceFirstOrder2D(kgrid,medium,source,sensor, ...
        'PMLSize',2,'PMLInside',false,'DataCast','single','PlotSim',false);

    %% Sauvegarde des donnees
    nom_fichier = sprintf('Sim_9_impacts_forme_%d.mat',forme);
    save(nom_fichier,'sensor_data','positions_sondes','impacts', ...
        'indices_impacts','dx','dy','SoundSpeed','Density','forme','noms_formes', ...
        'cercle','rectangle','trapeze','palette','forme_D','piano')
    fprintf('Enregistre : %s\n',nom_fichier)
end
