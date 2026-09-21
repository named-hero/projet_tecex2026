function comparaison=Tableau_comparaison(fichiers)
% ETAPE 5 : compare des fichiers Analyse_*.mat issus de Analyser_simulation.
% Aucune simulation ni nouveau calcul des correlations.
% Sans argument : selectionner les analyses avec Ctrl+clic.
if nargin<1 || isempty(fichiers)
    depart=fullfile(fileparts(mfilename('fullpath')),'resultats_simulation','analyses');
    if ~isfolder(depart), depart=pwd; end
    [f,d]=uigetfile({'*.mat','Analyses MATLAB (*.mat)'}, ...
        'Choisir les fichiers Analyse_...mat',fullfile(depart,'*.mat'),'MultiSelect','on');
    if isequal(f,0), comparaison=table(); return; end
    if ischar(f), f={f}; end
    fichiers=cellfun(@(x)fullfile(d,x),f,'UniformOutput',false);
end
if ischar(fichiers)||isstring(fichiers), fichiers=cellstr(fichiers); end
comparaison=table();
for k=1:numel(fichiers)
    [~,~,extension]=fileparts(fichiers{k});
    assert(strcmpi(extension,'.mat'), ...
        'Selectionnez le fichier Analyse_...mat, pas le CSV : %s',fichiers{k});
    contenu=whos('-file',fichiers{k});
    assert(any(strcmp({contenu.name},'stats')), ...
        'Ce fichier ne contient pas une analyse. Choisissez Analyse_...mat dans le dossier analyses : %s',fichiers{k});
    A=load(fichiers{k},'stats');
    assert(isfield(A,'stats') && isfield(A.stats,'methode'), ...
        'Choisir une analyse creee par Analyser_simulation.m : %s',fichiers{k});
    st=A.stats;
    ligne=table(string(fichiers{k}),string(st.fichier_source),string(st.nom_forme), ...
        string(st.materiau),string(st.methode),st.n_impacts, ...
        'VariableNames',{'Fichier_analyse','Fichier_simulation','Forme','Materiau','Methode','N_impacts'});
    ligne.Vitesse_m_s=NaN; ligne.Densite_kg_m3=NaN;
    if isfield(st,'parametres_materiau') && isstruct(st.parametres_materiau)
        m=st.parametres_materiau;
        if isfield(m,'sound_speed') && isscalar(m.sound_speed), ligne.Vitesse_m_s=m.sound_speed; end
        if isfield(m,'density') && isscalar(m.density), ligne.Densite_kg_m3=m.density; end
    end
    champs={'Rx','Ry','contraste'}; prefixes={'Rx_cm','Ry_cm','C'};
    for q=1:3
        a=st.agg.(champs{q}); prefix=prefixes{q};
        ligne.([prefix '_moy'])=a.moy;
        ligne.([prefix '_min'])=a.min;
        ligne.([prefix '_max'])=a.max;
        ligne.([prefix '_ecart_type'])=a.ecart_type;
        ligne.([prefix '_n_valides'])=a.n_valides;
    end
    ligne.Autre_max=max(st.confusion_max);
    ligne.Complete=all(isfinite(st.Rx)) && all(isfinite(st.Ry)) && all(isfinite(st.contraste));
    comparaison=[comparaison;ligne]; %#ok<AGROW>
end
assert(numel(unique(comparaison.Methode))==1, ...
    'Les methodes de resolution different : refaire les analyses avec la meme methode.');
disp(comparaison);
fprintf('Une ligne par simulation : aucune moyenne entre fichiers, aucune suppression de doublons.\n');
fprintf('Les ecarts-types decrivent la dispersion entre impacts, pas une incertitude experimentale.\n');
if any(~comparaison.Complete)
    warning('Certaines analyses sont incompletes. Leurs statistiques ne portent que sur les valeurs finies.');
end
[f,d]=uiputfile('*.csv','Enregistrer le tableau comparatif','Comparaison_formes_materiaux.csv');
if ~isequal(f,0), writetable(comparaison,fullfile(d,f)); end
end
