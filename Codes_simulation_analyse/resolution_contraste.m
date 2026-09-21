function stats = resolution_contraste(entree, methode)
% Calcul autonome : aucune simulation, aucune modification des donnees.
% stats = resolution_contraste('chemin/Sim_....mat');
% stats = resolution_contraste(load('chemin/Sim_....mat'));
% Sans argument : choisir un fichier de simulation.
% methode : 'absolue' (defaut, seuil 0.5) ou 'fond' (fond + demi-hauteur).
% Ne pas comparer des resolutions obtenues avec des methodes differentes.
% Correlation = maximum absolu de l'intercorrelation normalisee sur tous les retards.
% Contraste principal = 1 / moyenne des correlations aux autres impacts.
% Ecart-type : dispersion spatiale, pas incertitude de repetabilite.
if nargin<1 || isempty(entree)
    [f,d]=uigetfile('*.mat','Choisir les donnees de simulation');
    if isequal(f,0), stats=[]; return; end
    entree=fullfile(d,f);
end
if nargin<2, methode='absolue'; end
methode=validatestring(methode,{'absolue','fond'});
fichier='';
if ischar(entree) || (isstring(entree) && isscalar(entree))
    fichier=char(entree); S=load(fichier);
else
    S=entree;
end
assert(isstruct(S),'Fournir un fichier .mat ou une structure load.');
assert(all(isfield(S,{'sensor_data','positions_sondes','impacts', ...
    'dx','dy'})), ...
    'Il faut sensor_data, positions_sondes, impacts, dx et dy : fournir une simulation, pas seulement une forme.');
assert(size(S.impacts,2)==2 && size(S.impacts,1)>=2, ...
    'Il faut au moins deux impacts (colonnes [i j]).');
assert(~isempty(which('xcorr')), 'xcorr introuvable (Signal Processing Toolbox).');

assert(isscalar(S.dx)&&isfinite(S.dx)&&S.dx>0 && isscalar(S.dy)&&isfinite(S.dy)&&S.dy>0, 'dx et dy doivent etre positifs, en metres.');
assert(size(S.positions_sondes,2)==2 && size(S.sensor_data,1)==size(S.positions_sondes,1), 'Une ligne de signal par sonde est requise.');
assert(size(unique(S.positions_sondes,'rows'),1)==size(S.positions_sondes,1), 'Sondes dupliquees.');
assert(size(unique(S.impacts,'rows'),1)==size(S.impacts,1), 'Impacts dupliques.');
[ok,indices]=ismember(S.impacts,S.positions_sondes,'rows');
assert(all(ok),'Certains impacts sont absents des sondes.');
if isfield(S,'indices_impacts')
    assert(isequal(S.indices_impacts(:),indices(:)), 'indices_impacts incoherents avec positions_sondes.');
end
S.indices_impacts=indices;
signaux = double(S.sensor_data);
assert(all(isfinite(signaux(:))), 'Les signaux contiennent NaN ou Inf.');
energies = sqrt(sum(signaux.^2,2));
assert(all(energies>0), 'Au moins un signal est nul : simulation a rejouer.');
norm_signaux = signaux ./ energies;

n = size(S.impacts,1);
I = S.impacts(:,1);
J = S.impacts(:,2);

Rx = NaN(n,1); Ry = NaN(n,1);
contraste_profil_x = NaN(n,1); contraste_profil_y = NaN(n,1);
contraste_grille = NaN(n,1); confusion_max = NaN(n,1);
couleurs = zeros(n,n);
absc_x = cell(n,1); courbe_x = cell(n,1); seuil_x = NaN(n,1); base_x = NaN(n,1);
absc_y = cell(n,1); courbe_y = cell(n,1); seuil_y = NaN(n,1); base_y = NaN(n,1);

utiliser_indices = isfield(S,'indices_profils_x') && isfield(S,'indices_profils_y');
if isfield(S,'etendues_profils')
    etendues = S.etendues_profils(:);
else
    etendues = 6*ones(n,1);
end

for p = 1:n
    ref = S.indices_impacts(p);
    coeff = zeros(size(signaux,1),1);
    for q = 1:size(signaux,1)
        c = xcorr(norm_signaux(ref,:),norm_signaux(q,:));
        coeff(q) = max(abs(c));
    end
    couleurs(p,:) = coeff(S.indices_impacts).';
    autres = setdiff(1:n,p);
    contraste_grille(p) = 1/mean(couleurs(p,autres));
    confusion_max(p) = max(couleurs(p,autres));

    if utiliser_indices
        masque_x = S.indices_profils_x{p};
        masque_y = S.indices_profils_y{p};
    else
        masque_x = S.positions_sondes(:,2)==J(p) ...
            & abs(S.positions_sondes(:,1)-I(p))<=etendues(p);
        masque_y = S.positions_sondes(:,1)==I(p) ...
            & abs(S.positions_sondes(:,2)-J(p))<=etendues(p);
    end

    masque_x=profilValide(S,masque_x,p,1);
    masque_y=profilValide(S,masque_y,p,2);
    [ax,ox] = sort((S.positions_sondes(masque_x,1)-I(p))*S.dx*100);
    [ay,oy] = sort((S.positions_sondes(masque_y,2)-J(p))*S.dy*100);
    cx = coeff(masque_x); cx = cx(ox);
    cy = coeff(masque_y); cy = cy(oy);
    absc_x{p} = ax; courbe_x{p} = cx;
    absc_y{p} = ay; courbe_y{p} = cy;

    [Rx(p),seuil_x(p),base_x(p)] = largeurMiHauteur(ax,cx,methode);
    [Ry(p),seuil_y(p),base_y(p)] = largeurMiHauteur(ay,cy,methode);
    contraste_profil_x(p) = contrasteProfil(cx,base_x(p));
    contraste_profil_y(p) = contrasteProfil(cy,base_y(p));
end

stats.methode=methode; stats.fichier_source=fichier;
stats.n_impacts = n;
stats.Rx = Rx;
stats.Ry = Ry;
stats.contraste_profil_x = contraste_profil_x;
stats.contraste_profil_y = contraste_profil_y;
stats.contraste_profil = mean([contraste_profil_x contraste_profil_y],2,'omitnan');
stats.contraste_grille = contraste_grille;
stats.contraste = contraste_grille;
stats.confusion_max = confusion_max;
stats.couleurs = couleurs;
stats.absc_x = absc_x; stats.courbe_x = courbe_x;
stats.absc_y = absc_y; stats.courbe_y = courbe_y;
stats.seuil_x = seuil_x; stats.seuil_y = seuil_y;
stats.base_x = base_x; stats.base_y = base_y;

if isfield(S,'nom_forme')
    stats.nom_forme = char(S.nom_forme);
else
    stats.nom_forme = 'forme inconnue';
end
if isfield(S,'materiau') && isstruct(S.materiau) && isfield(S.materiau,'nom')
    stats.materiau = char(S.materiau.nom);
else
    stats.materiau = 'non_nomme';
end

stats.agg.Rx = resumerVecteur(Rx);
stats.agg.Ry = resumerVecteur(Ry);
stats.agg.contraste_profil = resumerVecteur(stats.contraste_profil);
stats.agg.contraste_grille = resumerVecteur(contraste_grille);
stats.agg.contraste = stats.agg.contraste_grille;
stats.agg.confusion_max = resumerVecteur(confusion_max);

stats.par_impact=table((1:n)',Rx,Ry,contraste_grille,confusion_max, ...
    'VariableNames',{'Impact','Rx_cm','Ry_cm','Contraste','Autre_max'});
Grandeur=["Rx_cm";"Ry_cm";"Contraste"];
champs={'Rx','Ry','contraste'}; Moyenne=zeros(3,1); Minimum=Moyenne; Maximum=Moyenne;
Ecart_type=Moyenne; N_valides=Moyenne; N_total=n*ones(3,1);
for k=1:3
    a=stats.agg.(champs{k}); Moyenne(k)=a.moy; Minimum(k)=a.min;
    Maximum(k)=a.max; Ecart_type(k)=a.ecart_type; N_valides(k)=a.n_valides;
end
stats.resume=table(Grandeur,Moyenne,Minimum,Maximum,Ecart_type,N_valides,N_total);
if isfield(S,'materiau'), stats.parametres_materiau=S.materiau; end
if isfield(S,'source_pos_x'), stats.source_pos_x=S.source_pos_x; end
if isfield(S,'source_pos_y'), stats.source_pos_y=S.source_pos_y; end
fprintf('\n%s / %s | methode : %s\n',stats.nom_forme,stats.materiau,methode);
disp(stats.par_impact); disp(stats.resume);
fprintf('Statistiques sur valeurs finies uniquement : verifier N_valides avant comparaison.\n');
n_incomplets = sum(~isfinite(Rx) | ~isfinite(Ry));
if n_incomplets > 0
    fprintf(['%s / %s : %d impact(s) sans Rx et/ou Ry mesurable ' ...
        '(passages au seuil non observes des deux cotes).\n'], ...
        stats.nom_forme,stats.materiau,n_incomplets);
end
end

function r = resumerVecteur(x)
valides = isfinite(x);
r.n_total = numel(x);
r.n_valides = sum(valides);
if r.n_valides == 0
    r.moy = NaN; r.min = NaN; r.max = NaN;
    r.ecart_type = NaN; 
    return
end
r.moy = mean(x(valides));
r.min = min(x(valides));
r.max = max(x(valides));
if r.n_valides >= 2
    r.ecart_type = std(x(valides),0);

else
    r.ecart_type = NaN;
    
end
end

function C = contrasteProfil(c,baseline)
if isempty(c) || ~isfinite(baseline) || baseline <= 0
    C = NaN;
    return
end
C = max(c) / baseline;
end

function [largeur,seuil,baseline] = largeurMiHauteur(x,c,methode)
largeur = NaN;
seuil = NaN;
baseline = NaN;
milieu = find(abs(x)<1e-10,1);
if isempty(milieu) || numel(x) < 3
    return
end
n = numel(x);
n_bord = max(1,round(0.25*n));
gauche_bord = c(1:min(n_bord,milieu-1));
droite_bord = c(max(milieu+1,n-n_bord+1):n);
bord = [gauche_bord(:); droite_bord(:)];
if isempty(bord)
    baseline = min(c);
else
    baseline = mean(bord);
end
Cmax = c(milieu);
if strcmp(methode,'absolue'), seuil=0.5*Cmax;
else, seuil=baseline+(Cmax-baseline)/2; end
gauche = find(c(1:milieu-1)<=seuil,1,'last');
droite_rel = find(c(milieu+1:end)<=seuil,1,'first');
if isempty(gauche) || isempty(droite_rel)
    return
end
droite = milieu + droite_rel;
if c(gauche+1)==c(gauche) || c(droite)==c(droite-1)
    return
end
xg = x(gauche)+(seuil-c(gauche))*(x(gauche+1)-x(gauche))/(c(gauche+1)-c(gauche));
xd = x(droite-1)+(seuil-c(droite-1))*(x(droite)-x(droite-1))/(c(droite)-c(droite-1));
largeur = xd-xg;
end

function ids=profilValide(S,selection,p,axe)
if islogical(selection), ids=find(selection); else, ids=selection(:); end
assert(all(isfinite(ids)&ids>=1&ids<=size(S.positions_sondes,1)&ids==round(ids)), 'Indices de profil invalides.');
autre=3-axe;
assert(all(S.positions_sondes(ids,autre)==S.impacts(p,autre)), 'Profil non aligne avec l impact.');
assert(any(ids==S.indices_impacts(p)), 'Reference absente du profil.');
delta=S.positions_sondes(ids,axe)-S.impacts(p,axe);
% Conserver uniquement les points contigus autour du centre, pas au-dela d'un trou.
retenus=delta==0;
for signe=[-1 1]
    k=1;
    while any(delta==signe*k)
        retenus=retenus | delta==signe*k; k=k+1;
    end
end
ids=ids(retenus);
end
