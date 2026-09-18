%% Installation
% Afin d'installer k-wave, référez-vous  au site http://www.k-wave.org/installation.php
% Vous aurez besoin de vous créer un compte afin d'y accéder.
% Assurez-vous que que la toolbox k-wave se situe AU DESSUS de la liste des
% path de votre matlab puisqu'elle écrase des fonctions natives de Matlab.
% Pour cette même raison, il serait judicieux de la remettre au bas de
% cette liste à la fin du mandat. 

%% Clear
clear all; clc

formes_a_tester = 4;

% 1 = rectangle
% 2 = trapeze
% 3 = trapeze avec deux coupes
% 4 = trapeze avec un trou
% 5 = trapeze avec coupes et trou
% 6 = polygone tres irregulier

noms_formes = { ...
    'Rectangle (reference)', ...
    'Trapeze', ...
    'Trapeze avec deux coupes', ...
    'Trapeze avec un trou', ...
    'Trapeze avec coupes et trou', ...
    'Polygone tres irregulier'};

%% Simulation grid parameter
Nx = 124;               % number of grid points in the x (row) direction
Ny = 60;               % number of grid points in the y (column) direction
dx = 5e-3;            % grid points spacing in the x direction [m]
dy = 5e-3;            % grid points spacing in the y direction [m]

kgrid = kWaveGrid(Nx, dx, Ny, dy);

SoundSpeed = 3000;      % Sound speed in the main material [m/s]
Density = 2500;         % Density of the main material [kg/m^3]


%% Changement du pas de temps

% % Optional, if set manually, both must be changed
% % -->
% % Attention le rapport entre la vitesse du son et le "dt" ne doit pas
% % être en dessous de ~5*10^9 pour eviter des erreurs numeriques.
% 
%
% kgrid.Nt = 8000;      % number of time steps
% kgrid.dt = 5*10^-7;   % time step [s]

for forme = formes_a_tester

fprintf('\nSimulation de la forme %d : %s\n', forme, noms_formes{forme});


%% Shape of the medium

% Definition des propriété de base du matériau de propagation
medium.sound_speed = SoundSpeed*ones(Nx, Ny);
medium.density = Density*ones(Nx, Ny);

% Definition des propriétés de simulation 
% (Ne pas toucher)
medium.alpha_coeff = 0.75;              % [dB/(MHz^y cm)]
medium.alpha_power = 1.5;


% Afin d'avoir une onde qui se reflete aux extremites, une partie du
% domaine doit avoir les caractéristiques de l'air. Donc :
% Vitesse du son : 330 m/s
% Densité : 10 kg/m^3 (Pas exactement comme l'air mais evite des erreurs numeriques)

airSpeed = 330;     % [m/s]
airDensity = 10;    % [kg/m^3]

for i = 1:Nx
    for j = 1:Ny
        if i < 4 || i > (Nx-4) || j < 4 || j > (Ny-4)
            medium.sound_speed(i,j) = airSpeed;
            medium.density(i,j) = airDensity;
        end
    end
end

%%Choix de la geometrie
switch forme

    case 1
        %% FORME 1 : rectangle
        % Aucune modification supplementaire.

    case 2
        %% FORME 2 : trapeze

        inclinaison = 0.10;
        %inclinaison = 0.06;
        %inclinaison = 0.10;
        %inclinaison = 0.14;

        for i = 4:(Nx-4)

            limite_j = (Ny-4) - round(inclinaison*(i-4));

            for j = 4:(Ny-4)

                if j > limite_j
                    medium.sound_speed(i,j) = airSpeed;
                    medium.density(i,j) = airDensity;
                end

            end
        end

    case 3
        %% FORME 3 : trapeze avec deux coupes differentes

        inclinaison = 0.10;

        % Dimensions de la premiere coupe
        longueur_i_1 = 24;
        longueur_j_1 = 12;

        % Dimensions de la deuxieme coupe
        longueur_i_2 = 18;
        longueur_j_2 = 10;


%{
Petite coupe
longueur_i_1 = 18;
longueur_j_1 = 8;

Coupe moyenne
longueur_i_1 = 27;
longueur_j_1 = 12;

Grande coupe
longueur_i_1 = 36;
longueur_j_1 = 16;
%}


        for i = 4:(Nx-4)
            for j = 4:(Ny-4)

                % Bord incline du trapeze
                limite_j = (Ny-4) - round(inclinaison*(i-4));
                hors_trapeze = j > limite_j;

                % Coupe au premier coin
                coupe_1 = (i-4)/longueur_i_1 ...
                         + (j-4)/longueur_j_1 <= 1;

                % Coupe au coin oppose
                coupe_2 = ((Nx-4)-i)/longueur_i_2 ...
                         + (j-4)/longueur_j_2 <= 1;

                if hors_trapeze || coupe_1 || coupe_2
                    medium.sound_speed(i,j) = airSpeed;
                    medium.density(i,j) = airDensity;
                end

            end
        end

    case 4
        %% FORME 4 : trapeze avec un trou

        inclinaison = 0.10;

        centre_trou_i = 75;
        centre_trou_j = 34;
        rayon_trou = 4;

%{
rayon_trou = 0; sans trou
rayon_trou = 2;  rayon de 1 cm
rayon_trou = 4;  rayon de 2 cm
rayon_trou = 6;  rayon de 3 cm

centre_trou_i = 75; pres d'un bord
centre_trou_j = 48;

centre_trou_i = 70; plus centre
centre_trou_j = 34;

centre_trou_i = 85; decentre autre coté
centre_trou_j = 25;

centre_trou_i = 35; plus pres d'une extremite
centre_trou_j = 30;
%}

        for i = 4:(Nx-4)
            for j = 4:(Ny-4)

                limite_j = (Ny-4) - round(inclinaison*(i-4));
                hors_trapeze = j > limite_j;

                trou = (i-centre_trou_i)^2 ...
                     + (j-centre_trou_j)^2 <= rayon_trou^2;

                if hors_trapeze || trou
                    medium.sound_speed(i,j) = airSpeed;
                    medium.density(i,j) = airDensity;
                end

            end
        end

    case 5
        %% FORME 5 : trapeze avec deux coupes et un trou

        inclinaison = 0.10;

        % Dimensions de la premiere coupe
        longueur_i_1 = 24;
        longueur_j_1 = 12;

        % Dimensions de la deuxieme coupe
        longueur_i_2 = 18;
        longueur_j_2 = 8;

        centre_trou_i = 75;
        centre_trou_j = 34;
        rayon_trou = 4;


        for i = 4:(Nx-4)
            for j = 4:(Ny-4)

                limite_j = (Ny-4) - round(inclinaison*(i-4));
                hors_trapeze = j > limite_j;

                coupe_1 = (i-4)/longueur_i_1 ...
                         + (j-4)/longueur_j_1 <= 1;

                coupe_2 = ((Nx-4)-i)/longueur_i_2 ...
                         + (j-4)/longueur_j_2 <= 1;

                trou = (i-centre_trou_i)^2 ...
                     + (j-centre_trou_j)^2 <= rayon_trou^2;

                if hors_trapeze || coupe_1 || coupe_2 || trou
                    medium.sound_speed(i,j) = airSpeed;
                    medium.density(i,j) = airDensity;
                end

            end
        end

    case 6
        %% FORME 6 : polygone tres irregulier
        % Deux coupes inclinees et une encoche rectangulaire.

        % Dimensions de la premiere coupe
        longueur_i_1 = 27;
        longueur_j_1 = 12;

        % Dimensions de la deuxieme coupe
        longueur_i_2 = 18;
        longueur_j_2 = 8;

        for i = 4:(Nx-4)
            for j = 4:(Ny-4)

                coupe_1 = (i-4)/longueur_i_1 ...
                         + (j-4)/longueur_j_1 <= 1;

                coupe_2 = ((Nx-4)-i)/longueur_i_2 ...
                         + (j-4)/longueur_j_2 <= 1;

                % Encoche sur le bord gauche
                encoche = i >= 55 && i <= 70 ...
                        && j >= 4 && j <= 10;

                if coupe_1 || coupe_2 || encoche
                    medium.sound_speed(i,j) = airSpeed;
                    medium.density(i,j) = airDensity;
                end

            end
        end

end

%% Define sensor
% On définit les capteurs de l'onde acoustique. On peut en definir
% plusieurs d'un même coup en ajoutant une paire de coordonnée sur la
% grille de simulation

clear sensor

impactXGrid = 20:2:104;     % [gridPoint]
impactYGrid = 12;     % [gridPoint]

% On transforme les points de la grille de simulation en position
% cartésienne.

sensor.mask = zeros(Nx, Ny);
for numero_impact = 1:length(impactXGrid)
    sensor.mask(impactXGrid(numero_impact), impactYGrid) = 1;
end

%% Source definition
% De même, la source est défini grâce à une paire de point sur la grille de
% simulation. On crée un disque de la taille d'une doigt pour l'impact.
% Attention à ce que toute la source soit à l'intérieur du matériau simulé.
% Dans le cas présent, la source ne doit pas être dans un périmètre de 4dx
% du bord.

clear source

sourceGrid = [45, 35];
source_radius = floor(0.01/dx);         % [grid points] (Taille d'un doigt)
source_magnitude = 10;                  % [Pa]
source_1 = source_magnitude*makeDisc(Nx, Ny, sourceGrid(1), sourceGrid(2), source_radius);

source.p0 = source_1;

% Verification des positions d'impact
for numero_impact = 1:length(impactXGrid)
    if medium.sound_speed(impactXGrid(numero_impact), impactYGrid) == airSpeed
        error('Une position d''impact est dans l''air.')
    end
end

% Verification de la position du piezo utilise comme source par reciprocite
masque_source = source_1 > 0;

if any(medium.sound_speed(masque_source) == airSpeed)
    error('Le piezo touche une region d''air.')
end

% Pour l'affichage, on transforme les points de la grille de simulation en
% position cartésienne. 
source_x_pos = kgrid.x_vec(sourceGrid(1));         % [grid points]
source_y_pos = kgrid.y_vec(sourceGrid(2));         % [grid points]

%% Visualisation de la grille de simulation
% On peut s'assurer que tous nos paramètres sont correctement défini à
% l'aide d'un graphique.

figure('Name', ['Geometrie - ' noms_formes{forme}]);
imagesc(kgrid.y_vec*1e3, kgrid.x_vec*1e3, medium.sound_speed); axis image
ylabel('x - position [mm]')
xlabel('y - position [mm]')
c = colorbar;
c.Label.String = 'Speed of sound';
hold on;
plot(source_y_pos*1e3, source_x_pos*1e3, 'r.', 'MarkerSize', 18)
plot(kgrid.y_vec(impactYGrid)*1e3*ones(size(impactXGrid)), ...
     kgrid.x_vec(impactXGrid)*1e3, 'b+')
legend('Capteur piezo', 'Impacts')
title(noms_formes{forme})
drawnow

%% Simulation
% Pour accélérer la simulation, on réduit la taille du Perfectly Matching
% Layer (https://en.wikipedia.org/wiki/Perfectly_matched_layer).

sensor_data = kspaceFirstOrder2D(kgrid, medium, source, sensor,...
    'PMLSize', 2, 'PMLInside', false, 'DataCast', 'single', ...
    'PlotSim', false);

%% Visulation des données de simulation
figure('Name', ['Signal - ' noms_formes{forme}]);
normes_signaux = sqrt(sum(sensor_data.^2, 2));
sensor_data_normalise = sensor_data./normes_signaux;
plot(kgrid.t_array*10^3, sensor_data_normalise')
xlabel('Temps [ms]')
ylabel('Amplitude')
title(['Amplitude mesuree - ' noms_formes{forme}])
drawnow

%% Sauvegarde des données
% Sauvegarder les données pour les réutiliser plus tard, où pour les
% exporter vers python. Pour load dans python, utiliser scipy.io.loadmat()

nom_fichier = sprintf('Sim_forme_%d.mat', forme);
save(nom_fichier, 'sensor_data', 'impactXGrid', ...
    'impactYGrid', 'forme', 'sourceGrid')

end

