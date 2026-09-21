%% Installation
% Ajouter k-Wave au chemin MATLAB avant de lancer ce script.

%% Initialisation variables
clear; clc; close all

% FORMES : 1=cercle, 2=rectangle, 3=trapeze, 4=PNG 1, 5=PNG 2, etc.
% PNG : silhouette NOIRE PLEINE sur fond BLANC. Trous en blanc.
% Un contour seul ou une photo de piano ne constitue pas un masque de plaque.
% L'image est ajustee a la grille sans modifier ses proportions.
formes_custom_plaques = {'',''}; % Vide : choix du PNG dans une fenetre.
% Exemple pour trois dessins : {'palette.png','forme_D.png','piano.png'};
png_matiere_sombre = false; % false pour une silhouette blanche sur fond noir.
png_seuil = 0.5;           % Seuil de luminosite entre 0 et 1.
formes_basique = {'Cercle','Rectangle','Trapeze trou et deux coupes','Forme en D'};
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

% Nombre d'impacts par defaut pour une forme PNG (clics).
% Pour les formes basiques, c'est le nombre de lignes dans
% impacts_formes_basique{k} qui compte : tes coequipiers peuvent en mettre
% 6, 9, 12... sans changer l'analyse. Les positions et la source sont
% RELUES dans le .mat : tu n'as pas a les connaitre a l'avance.
nb_impacts_png = 9;

% PARAMETRES A MODIFIER
indices_formes = 1:6; % Trois formes classiques + un dessin PNG.
% Mettre 4 pour le PNG seul, ou 1:3 pour les trois formes classiques.
assert(all(ismember(indices_formes,1:(4+numel(formes_custom_plaques)))), ...
    'Ajoutez les chemins PNG dans formes_custom_plaques pour ces indices.');

formes_a_tester = struct('index',{},'basique',{});
for n = indices_formes
    formes_a_tester(end+1) = struct('index', n, 'basique', n <= 4); %#ok<SAGROW>
end

% Valeurs provisoires du template : a remplacer par acier / aluminium / plastique.
% Pour comparer plusieurs materiaux : ajoutez des entrees et mettez
% indices_materiaux = 1:numel(materiaux). Chaque couple (forme, materiau)
% produit un fichier .mat distinct (pas d'ecrasement).
materiaux = struct( ...
    'nom',          {'provisoire'}, ...
    'sound_speed',  {3000}, ...
    'density',      {2500});
indices_materiaux = 1;
assert(all(ismember(indices_materiaux,1:numel(materiaux))), ...
    'indices_materiaux hors des materiaux definis.');

calcul_simulation = true;   % false : afficher seulement les geometries.
% Ce script effectue uniquement la simulation et la sauvegarde.

% Les resultats sont places a cote de ce script, dans resultats_simulation.
dossier_code = fileparts(mfilename('fullpath'));
if isempty(dossier_code), dossier_code = pwd; end
addpath(dossier_code);
dossier_resultats = fullfile(dossier_code,'resultats_simulation');
if ~isfolder(dossier_resultats)
    mkdir(dossier_resultats);
end
fichiers_generes = {};
% Verification de k-Wave. Aucun remplacement des fonctions de la toolbox.
if calcul_simulation
    assert(~isempty(which('kWaveGrid')), ...
        'k-Wave introuvable : ajoutez son dossier principal au chemin MATLAB.');
    assert(~isempty(which('kspaceFirstOrder2D')), ...
        'Installation k-Wave incomplete : kspaceFirstOrder2D est introuvable.');
    try
        makeDisc(12,12,6,6,2);
    catch erreur
        error('Installation k-Wave a corriger avant la simulation : %s',erreur.message);
    end
end

%% Simulation grid parameter
Nx = 124;
Ny = 60;
dx = 5e-3;
dy = 5e-3;
if calcul_simulation
    kgrid=kWaveGrid(Nx,dx,Ny,dy);
else
    kgrid=struct('x_vec',(-floor(Nx/2):ceil(Nx/2)-1)'*dx, ...
                'y_vec',(-floor(Ny/2):ceil(Ny/2)-1)'*dy);
end
airSpeed = 330;
airDensity = 10;

%% Boucle de simulation
for imat = indices_materiaux
    materiau = materiaux(imat);
    fprintf('\n===== Materiau : %s (c = %g m/s, rho = %g kg/m^3) =====\n', ...
        materiau.nom,materiau.sound_speed,materiau.density);
for forme = formes_a_tester
    if forme.basique
        nom_forme = formes_basique{forme.index};
    else
        pathStr = formes_custom_plaques{forme.index-4};
        if isempty(pathStr)
            [nom_png,dossier_png]=uigetfile('*.png','Choisir une silhouette PNG');
            if isequal(nom_png,0), error('Selection du PNG annulee.'); end
            pathStr=fullfile(dossier_png,nom_png);
        elseif ~isfile(pathStr)
            pathStr=fullfile(dossier_code,pathStr);
        end
        assert(isfile(pathStr),'PNG introuvable : %s',pathStr);
        [~, name, ~] = fileparts(pathStr);
        nom_forme = name;
    end
    medium = struct(); source = struct(); sensor = struct();
    source_pos_x=62; source_pos_y=9; source_radius=2;
    provenance_png='';
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
             case 4  % D : cote plat a gauche, cote bombe a droite
                forme_D = D_shape(Nx/2);
                matiere = J>=forme_D.bord_plat_j ...
                    & ((I-forme_D.centre_i)/forme_D.rayon_i).^2 ...
                    + ((J-forme_D.bord_plat_j)/forme_D.rayon_arrondi_j).^2 <= 1;
        end
        matiere = matiere & bordure;
        medium.sound_speed(matiere) = materiau.sound_speed;
        medium.density(matiere) = materiau.density;
        impacts = impacts_formes_basique{forme.index};

    else
        provenance_png=pathStr;
        matiere=masqueDepuisPNG(pathStr,bordure,png_matiere_sombre,png_seuil);
        medium.sound_speed(matiere)=materiau.sound_speed;
        medium.density(matiere)=materiau.density;
        [impacts,position_fixe]=chargerOuPlacerPoints( ...
            kgrid,medium.sound_speed,matiere,nom_forme,source_radius, ...
            dossier_resultats,nb_impacts_png);
        source_pos_x=position_fixe(1); source_pos_y=position_fixe(2);
    end
    n_impacts = size(impacts,1);
    assert(n_impacts>=2 && size(impacts,2)==2 && all(isfinite(impacts(:))) ...
        && all(impacts(:)==round(impacts(:))) ...
        && size(unique(impacts,'rows'),1)==n_impacts, ...
        'Il faut au moins deux impacts distincts, en indices entiers [i j].');
    etendues_profils = 6*ones(n_impacts,1);
    pas_profil = -6:6;  % 0,5 cm par pas, de -3 a +3 cm.
    sondes = impacts;
    profils_x=cell(n_impacts,1); profils_y=cell(n_impacts,1);
    for p = 1:size(impacts, 1)
        pas_profil_impact = pas_profil;
        if forme.basique && forme.index == 1 ...
                && exist('cercle','var') ...
                && impacts(p,2)==cercle.centre_j ...
                && impacts(p,1)~=cercle.centre_i
            pas_profil_impact = -10:10;
        end
        etendues_profils(p) = max(abs(pas_profil_impact));
        profils_x{p}=profilContinu(matiere,impacts(p,:),[1 0],etendues_profils(p));
        profils_y{p}=profilContinu(matiere,impacts(p,:),[0 1],etendues_profils(p));
        if size(profils_x{p},1)<2*etendues_profils(p)+1 ...
                || size(profils_y{p},1)<2*etendues_profils(p)+1
            fprintf('Impact %d : profil limite par un bord/trou ; Rx ou Ry peut rester NaN.\n',p);
        end
        sondes=[sondes;profils_x{p};profils_y{p}]; 
    end
    sondes = unique(sondes,'rows');
    if any(sondes(:,1)<1| sondes(:,2)<1 | sondes(:,1)>Nx | sondes(:,2)>Ny) ...
            || any(~matiere(sub2ind([Nx Ny],sondes(:,1),sondes(:,2))))
        error('Forme %s : un impact ou une sonde auxiliaire est dans l''air.',nom_forme)
    end
    sensor.mask = false(Nx,Ny);
    sensor.mask(sub2ind([Nx Ny],sondes(:,1),sondes(:,2))) = true;
    [sensorI,sensorJ] = ind2sub([Nx Ny],find(sensor.mask));
    positions_sondes = [sensorI sensorJ];
    [ok, indices_impacts] = ismember(impacts,positions_sondes,'rows');
    assert(all(ok),'Impossible d''associer les impacts aux signaux.')
    indices_profils_x=cell(n_impacts,1); indices_profils_y=cell(n_impacts,1);
    for p=1:n_impacts
        [okx,indices_profils_x{p}]=ismember(profils_x{p},positions_sondes,'rows');
        [oky,indices_profils_y{p}]=ismember(profils_y{p},positions_sondes,'rows');
        assert(all(okx)&&all(oky),'Profil non retrouve dans les sondes.');
    end

    %% Source definition
    source_magnitude = 10;
    if calcul_simulation
        source.p0 = source_magnitude * makeDisc(Nx,Ny, ...
            source_pos_x,source_pos_y,source_radius);
    else
        source.p0 = source_magnitude * double( ...
            (I-source_pos_x).^2+(J-source_pos_y).^2 <= source_radius^2);
    end
    if any(~matiere(source.p0>0))
        error('Forme %s : le disque de la source touche l''air.',nom_forme)
    end

    %% Visualisation de la grille de simulation (identique formes basiques et PNG)
    afficherGeometrie(kgrid,medium.sound_speed,impacts,source_pos_x,source_pos_y,nom_forme);
    if ~calcul_simulation
        fprintf('Forme %s : geometrie affichee; simulation ignoree.\n',nom_forme)
        continue
    end

    %% Simulation
    fprintf(['Simulation %s / %s (%d sondes virtuelles).\n' ...
        'k-Wave tourne sans animation : MATLAB peut sembler fige quelques minutes.\n'], ...
        nom_forme,materiau.nom,size(positions_sondes,1));
    sensor_data = kspaceFirstOrder2D(kgrid,medium,source,sensor, ...
        'PMLSize',2,'PMLInside',false,'DataCast','single', ...
        'PlotSim',false,'PlotPML',false);
    fprintf('k-Wave termine pour %s.\n',nom_forme);

    %% Sauvegarde des donnees
    slug_forme = regexprep(char(nom_forme),'[^\w]+','_');
    slug_mat = regexprep(char(materiau.nom),'[^\w]+','_');
    if forme.basique
        nom_fichier = sprintf('Sim_%d_impacts_forme_%d_%s.mat',n_impacts,forme.index,slug_mat);
    else
        nom_fichier = sprintf('Sim_%d_impacts_custom_%d_%s_%s.mat',n_impacts,forme.index,slug_forme,slug_mat);
    end
    [~,base_nom]=fileparts(nom_fichier);
    nom_fichier = fullfile(dossier_resultats,[base_nom '_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS')) '.mat']);
    save(nom_fichier,'sensor_data','positions_sondes','impacts', ...
        'indices_impacts','dx','dy','materiau','forme','nom_forme','matiere', ...
        'etendues_profils','source_pos_x','source_pos_y','Nx','Ny', ...
        'indices_profils_x','indices_profils_y','provenance_png');
    fichiers_generes{end+1} = nom_fichier; 
    fprintf('Enregistre : %s\n',nom_fichier);
end
end

%% Fonctions locales : reglages des contours en points de grille (5 mm).
% i augmente vers le bas, j vers la droite.
function rectangle = Rectangle(width, height)
    rectangle.i_min = 4; rectangle.i_max = 4 + width;
    rectangle.j_min = 4; rectangle.j_max = 4 + height;
end

function cercle = Cercle(x, y, rayon)
    cercle.centre_i = x;
    cercle.centre_j = y;
    cercle.rayon = rayon;
end

function trapeze = Trapeze()
    trapeze.inclinaison = 0.10;
    trapeze.i_min = 4; trapeze.i_max = 120;
    trapeze.j_min = 4; trapeze.j_max = 56;
    trapeze.coupe_1_i = 24; trapeze.coupe_1_j = 12;
    trapeze.coupe_2_i = 18; trapeze.coupe_2_j = 8;
    trapeze.trou_i = 108; trapeze.trou_j = 18; trapeze.rayon_trou = 4;
end

function forme_D = D_shape(x)
    forme_D.centre_i = x; forme_D.rayon_i = 58; 
    forme_D.bord_plat_j = 4; forme_D.rayon_arrondi_j = 52;
end

function fig = afficherGeometrie(kgrid,carte,impacts,si,sj,nom)
    fig = figure('Name',nom,'Color','w');
    imagesc(kgrid.y_vec*1e3,kgrid.x_vec*1e3,carte);
    axis image; colormap(parula(256)); colorbar; hold on
    h1 = plot(kgrid.y_vec(impacts(:,2))*1e3, ...
        kgrid.x_vec(impacts(:,1))*1e3,'b+','MarkerSize',10,'LineWidth',1.3);
    h2 = plot(kgrid.y_vec(sj)*1e3, ...
        kgrid.x_vec(si)*1e3,'ro','MarkerFaceColor','r');
    for p = 1:size(impacts,1)
        if impacts(p,1)==0, continue; end
        text(kgrid.y_vec(impacts(p,2))*1e3+4, ...
            kgrid.x_vec(impacts(p,1))*1e3,num2str(p),'Color','k');
    end
    title(nom,'Interpreter','none');
    xlabel('Position y [mm]'); ylabel('Position x [mm]');
    legend([h1 h2],{sprintf('Impacts (N = %d)',size(impacts,1)), ...
        'Point fixe (source simulee)'},'Location','southoutside');
    drawnow;
end

function [impacts,fixe] = chargerOuPlacerPoints(kgrid,carte,matiere,nom,rayon,dossier_resultats,nb_defaut)
    slug = regexprep(char(nom),'[^\w]+','_');
    fichier_placement = fullfile(dossier_resultats,['placement_' slug '.mat']);
    if isfile(fichier_placement)
        choix = questdlg( ...
            sprintf('Reutiliser le placement enregistre pour %s ?',nom), ...
            'Placement','Oui','Non','Oui');
        if strcmp(choix,'Oui')
            P = load(fichier_placement);
            assert(isfield(P,'matiere') && isequal(P.matiere,matiere), ...
                'La geometrie a change. Relancez et choisissez Non pour replacer les points.');
            impacts = P.impacts;
            fixe = P.fixe;
            fprintf('Placement recharge (%d impacts) : %s\n',size(impacts,1),fichier_placement);
            return
        end
    end
    [impacts,fixe] = placerPoints(kgrid,carte,matiere,nom,rayon,nb_defaut);
    save(fichier_placement,'impacts','fixe','matiere');
    fprintf('Placement enregistre : %s\n',fichier_placement);
end

function matiere=masqueDepuisPNG(fichier,bordure,sombre,seuil)
    [im,map,alpha]=imread(fichier);
    if ~isempty(map)
        im=ind2rgb(im,map);
    elseif isinteger(im)
        im=double(im)/double(intmax(class(im)));
    else
        im=double(im);
    end
    if ndims(im)==3
        gris=0.2989*im(:,:,1)+0.5870*im(:,:,2)+0.1140*im(:,:,3);
    else
        gris=im;
    end
    if sombre, masque=gris<seuil; else, masque=gris>seuil; end
    if ~isempty(alpha)
        if isinteger(alpha), alpha=double(alpha)/double(intmax(class(alpha))); end
        masque=masque & alpha>0.5;
    end
    [rr,cc]=find(masque);
    assert(~isempty(rr),'Aucune matiere detectee : verifier les couleurs du PNG.');
    masque=masque(min(rr):max(rr),min(cc):max(cc));
    [br,bc]=find(bordure);
    hmax=max(br)-min(br)+1; wmax=max(bc)-min(bc)+1;
    [h0,w0]=size(masque);
    echelle=min(hmax/h0,wmax/w0);
    h=max(1,min(hmax,round(h0*echelle)));
    w=max(1,min(wmax,round(w0*echelle)));
    ri=min(h0,max(1,round(((1:h)-0.5)*h0/h+0.5)));
    cj=min(w0,max(1,round(((1:w)-0.5)*w0/w+0.5)));
    i0=min(br)+floor((hmax-h)/2); j0=min(bc)+floor((wmax-w)/2);
    matiere=false(size(bordure));
    matiere(i0:i0+h-1,j0:j0+w-1)=masque(ri,cj);
    assert(any(matiere(:)),'La forme disparait sur la grille de 5 mm.');
end

function [impacts,fixe]=placerPoints(kgrid,carte,matiere,nom,rayon,nb_defaut)
    % Meme axes, colorbar et unites que les formes basiques.
    if nargin<6 || isempty(nb_defaut), nb_defaut = 9; end
    rep = inputdlg( ...
        {'Nombre d''impacts a cliquer (ensuite 1 clic pour la source) :'}, ...
        'Placement',1,{num2str(nb_defaut)});
    if isempty(rep)
        error('Placement annule : relancez main2 pour recommencer.');
    end
    n_imp = round(str2double(rep{1}));
    assert(isfinite(n_imp) && n_imp>=2, 'Il faut au moins 2 impacts.');
    [nx,ny]=size(matiere);
    [ii,jj]=ndgrid(1:nx,1:ny);
    fig=figure('Name',['Placement : ' nom],'Color','w');
    imagesc(kgrid.y_vec*1e3,kgrid.x_vec*1e3,carte);
    axis image; colormap(parula(256)); colorbar; hold on
    xlabel('Position y [mm]'); ylabel('Position x [mm]');
    h1 = plot(nan,nan,'b+','MarkerSize',10,'LineWidth',1.3);
    h2 = plot(nan,nan,'ro','MarkerFaceColor','r');
    legend([h1 h2],{sprintf('Impacts (N = %d)',n_imp), ...
        'Point fixe (source simulee)'},'Location','southoutside');
    impacts=zeros(n_imp,2); fixe=[];
    fprintf(['\n%s : cliquez %d impacts (croix bleues) puis le point fixe (rond rouge).\n' ...
        'Clic gauche dans la matiere. Echap pour annuler.\n'],nom,n_imp);
    for p=1:(n_imp+1)
        valide=false;
        while ~valide
            if p<=n_imp
                titre=sprintf('%s : cliquez l''impact %d/%d (croix bleue)',nom,p,n_imp);
            else
                titre='Cliquez le point fixe (rond rouge, capteur / source simulee)';
            end
            title({titre,'Meme echelle [mm] que les formes basiques. Echap pour annuler.'}, ...
                'Interpreter','none');
            drawnow;
            [x_mm,y_mm,bouton]=ginput(1);
            if isempty(bouton)||bouton==27
                close(fig);
                error('Placement annule : relancez main2 pour recommencer.');
            end
            if bouton~=1, continue; end
            [~,i]=min(abs(kgrid.x_vec*1e3-y_mm));
            [~,j]=min(abs(kgrid.y_vec*1e3-x_mm));
            if i<1||i>nx||j<1||j>ny||~matiere(i,j)
                fprintf('Cliquez a l''interieur de la matiere (zone coloree, pas l''air).\n');
                continue
            end
            if p<=n_imp
                if ismember([i j],impacts(1:p-1,:),'rows')
                    fprintf('Ce point est deja utilise.\n'); continue
                end
                impacts(p,:)=[i j];
                plot(kgrid.y_vec(j)*1e3,kgrid.x_vec(i)*1e3,'b+','MarkerSize',10,'LineWidth',1.5);
                text(kgrid.y_vec(j)*1e3+4,kgrid.x_vec(i)*1e3,num2str(p),'Color','k');
                valide=true;
            else
                disque=(ii-i).^2+(jj-j).^2<=rayon^2;
                if i-rayon<1||i+rayon>nx||j-rayon<1||j+rayon>ny ...
                        ||any(~matiere(disque)) ...
                        ||any(disque(sub2ind([nx ny],impacts(:,1),impacts(:,2))))
                    fprintf('Placez le point fixe plus loin du bord, des trous et des impacts.\n');
                    continue
                end
                fixe=[i j];
                plot(kgrid.y_vec(j)*1e3,kgrid.x_vec(i)*1e3,'ro','MarkerFaceColor','r');
                valide=true;
            end
        end
    end
    close(fig);
end

function points=profilContinu(matiere,centre,direction,etendue)
    points=centre;
    for signe=[-1 1]
        for k=1:etendue
            q=centre+signe*k*direction;
            if q(1)<1||q(1)>size(matiere,1)||q(2)<1||q(2)>size(matiere,2) ...
                    ||~matiere(q(1),q(2))
                break
            end
            points(end+1,:)=q; 
        end
    end
    points=sortrows(points);
end
