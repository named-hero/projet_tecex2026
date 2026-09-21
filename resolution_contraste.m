function stats = resolution_contraste(S)
%RESOLUTION_CONTRASTE  Rx, Ry et contrastes pour N impacts (pas seulement 9).
%
%   stats = resolution_contraste(S)
%
% S : structure issue de load() d'un fichier Sim_*_impacts_*.mat (main2.m).
% Le nombre d'impacts et leurs positions sont lus dans S.impacts :
% tu n'as pas a les connaitre a l'avance.
%
% Definitions (manuel, section 3.5 / Figure 4) :
%   - Resolution Rx, Ry : largeur a mi-hauteur du pic de correlation le long
%     d'une rangee / colonne, seuil pris A MI-CHEMIN entre le sommet et la
%     ligne de base locale (moyenne des bords du profil).
%   - Contraste de profil : Cmax / ligne_de_base (meme figure).
%
% Contraste de grille :
%   1 / moyenne des correlations avec les (N-1) autres impacts.
%
% Incertitudes : les N impacts forment l'echantillon. Pour chaque grandeur
% on donne moyenne, min, max, ecart-type d'echantillon (N-1) et incertitude
% type sur la moyenne (ecart-type / sqrt(N_valides)).

assert(all(isfield(S,{'sensor_data','positions_sondes','impacts', ...
    'indices_impacts','dx','dy'})), ...
    'Champs manquants : relancez main2.m pour regenerer ce fichier.');
assert(size(S.impacts,2)==2 && size(S.impacts,1)>=2, ...
    'Il faut au moins deux impacts (colonnes [i j]).');
assert(~isempty(which('xcorr')), 'xcorr introuvable (Signal Processing Toolbox).');

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

    [ax,ox] = sort((S.positions_sondes(masque_x,1)-I(p))*S.dx*100);
    [ay,oy] = sort((S.positions_sondes(masque_y,2)-J(p))*S.dy*100);
    cx = coeff(masque_x); cx = cx(ox);
    cy = coeff(masque_y); cy = cy(oy);
    absc_x{p} = ax; courbe_x{p} = cx;
    absc_y{p} = ay; courbe_y{p} = cy;

    [Rx(p),seuil_x(p),base_x(p)] = largeurMiHauteur(ax,cx);
    [Ry(p),seuil_y(p),base_y(p)] = largeurMiHauteur(ay,cy);
    contraste_profil_x(p) = contrasteProfil(cx,base_x(p));
    contraste_profil_y(p) = contrasteProfil(cy,base_y(p));
end

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

n_incomplets = n - min(stats.agg.Rx.n_valides,stats.agg.Ry.n_valides);
if n_incomplets > 0
    fprintf(['%s / %s : %d impact(s) sans Rx et/ou Ry mesurable ' ...
        '(pic plus large que le profil sonde).\n'], ...
        stats.nom_forme,stats.materiau,n_incomplets);
end
end

function r = resumerVecteur(x)
valides = ~isnan(x);
r.n_total = numel(x);
r.n_valides = sum(valides);
if r.n_valides == 0
    r.moy = NaN; r.min = NaN; r.max = NaN;
    r.ecart_type = NaN; r.incertitude = NaN;
    return
end
r.moy = mean(x(valides));
r.min = min(x(valides));
r.max = max(x(valides));
if r.n_valides >= 2
    r.ecart_type = std(x(valides),0);
    r.incertitude = r.ecart_type / sqrt(r.n_valides);
else
    r.ecart_type = NaN;
    r.incertitude = NaN;
end
end

function C = contrasteProfil(c,baseline)
if isempty(c) || ~isfinite(baseline) || baseline <= 0
    C = NaN;
    return
end
C = max(c) / baseline;
end

function [largeur,seuil,baseline] = largeurMiHauteur(x,c)
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
seuil = baseline + (Cmax-baseline)/2;
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
