%% Installation
% Afin d'installer k-wave, référez-vous  au site http://www.k-wave.org/installation.php
% Vous aurez besoin de vous créer un compte afin d'y accéder.
% Assurez-vous que que la toolbox k-wave se situe AU DESSUS de la liste des
% path de votre matlab puisqu'elle écrase des fonctions natives de Matlab.
% Pour cette même raison, il serait judicieux de la remettre au bas de
% cette liste à la fin du mandat. 

%% Clear
clear all; clc

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

% Pour modifier la geometrie on peut ajouter des conditions comme ici
% creer un trou dans la surface.

for i = 1:Nx
    for j = 1:Ny
        if i > 70 && i < 80 && j >= (Ny/4-8) && j <= (Ny/4+8)
            medium.sound_speed(i,j) = airSpeed;
            medium.density(i,j) = airDensity;
        elseif  j >= 25 && j <= 18 && i >= 45 && i <= 50 ||  j <= (24-i/2)
            medium.sound_speed(i,j) = airSpeed;
            medium.density(i,j) = airDensity;
        end
    end
end
    
% Ou similairement, des coupes.

for i = 1:Nx
    for j = 1:Ny
        if i > 70 && i < 80 && j >= (Ny/4-8) && j <= (Ny/4+8)
            medium.sound_speed(i,j) = airSpeed;
            medium.density(i,j) = airDensity;
        end
    end
end

%% Define sensor
% On définit les capteurs de l'onde acoustique. On peut en definir
% plusieurs d'un même coup en ajoutant une paire de coordonnée sur la
% grille de simulation

clear sensor

sensorXGrid = [48];     % [gridPoint]
sensorYGrid = [48];     % [gridPoint]

% On transforme les points de la grille de simulation en position
% cartésienne.

sensor.mask = [kgrid.x_vec(sensorXGrid)'; kgrid.y_vec(sensorYGrid)'];

%% Source definition
% De même, la source est défini grâce à une paire de point sur la grille de
% simulation. On crée un disque de la taille d'une doigt pour l'impact.
% Attention à ce que toute la source soit à l'intérieur du matériau simulé.
% Dans le cas présent, la source ne doit pas être dans un périmètre de 4dx
% du bord.

sourceGrid = [91, 12];
source_radius = floor(0.01/dx);         % [grid points] (Taille d'un doigt)
source_magnitude = 10;                  % [Pa]
source_1 = source_magnitude*makeDisc(Nx, Ny, sourceGrid(1), sourceGrid(2), source_radius);

source.p0 = source_1;

% Pour l'affichage, on transforme les points de la grille de simulation en
% position cartésienne. 
source_x_pos = kgrid.x_vec(sourceGrid(1));         % [grid points]
source_y_pos = kgrid.y_vec(sourceGrid(2));         % [grid points]

%% Visualisation de la grille de simulation
% On peut s'assurer que tous nos paramètres sont correctement défini à
% l'aide d'un graphique.

figure;
imagesc(kgrid.y_vec*1e3, kgrid.x_vec*1e3, medium.sound_speed); axis image
ylabel('y - position [mm]')
xlabel('x - position [mm]')
c = colorbar;
c.Label.String = 'Speed of sound';
hold on;
plot(sensor.mask(2,:)*1e3, sensor.mask(1,:)*1e3, 'r.')
plot(source_y_pos*1e3, source_x_pos*1e3, 'b+')
legend('Sensor', 'Source')

%% Simulation
% Pour accélérer la simulation, on réduit la taille du Perfectly Matching
% Layer (https://en.wikipedia.org/wiki/Perfectly_matched_layer).

sensor_data = kspaceFirstOrder2D(kgrid, medium, source, sensor,...
    'PMLSize', 2, 'PMLInside', false, 'DataCast', 'single');

%% Visulation des données de simulation
figure;
plot(kgrid.t_array*10^3, sensor_data/norm(sensor_data))
xlabel('Temps [ms]')
ylabel('Amplitude')
title("Amplitude de l'onde mesuree au capteur")


%% Sauvegarde des données
% Sauvegarder les données pour les réutiliser plus tard, où pour les
% exporter vers python. Pour load dans python, utiliser scipy.io.loadmat()

save('Sim1.mat', 'sensor_data')


