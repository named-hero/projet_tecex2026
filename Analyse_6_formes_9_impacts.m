function synthese = Analyse_6_formes_9_impacts(selection)
%ANALYSE_6_FORMES_9_IMPACTS  Profils, cartes et stats a partir de main2.m.
%
%   synthese = Analyse_6_formes_9_impacts()
%   synthese = Analyse_6_formes_9_impacts(3)
%   synthese = Analyse_6_formes_9_impacts(fichiers_generes)

dossier_code = fileparts(mfilename('fullpath'));
addpath(dossier_code);
dossier_resultats = fullfile(dossier_code,'resultats_simulation');
if nargin < 1
    liste = listerFichiersSim(dossier_resultats);
    selection = arrayfun(@(f) fullfile(f.folder,f.name),liste,'UniformOutput',false);
end
if isnumeric(selection)
    validateattributes(selection,{'numeric'},{'vector','integer','>=',1});
    fichiers = {};
    for n = selection(:).'
        motif = fullfile(dossier_resultats,sprintf('Sim_*_impacts_forme_%d*.mat',n));
        liste = dir(motif);
        fichiers = [fichiers; arrayfun(@(f) fullfile(f.folder,f.name),liste,'UniformOutput',false)]; %#ok<AGROW>
    end
elseif iscell(selection)
    fichiers = selection;
elseif ischar(selection) || isstring(selection)
    fichiers = cellstr(selection);
else
    error('Selection attendue : numeros de formes ou chemins de fichiers.');
end
assert(~isempty(which('resolution_contraste')), ...
    'Placez resolution_contraste.m dans le meme dossier que ce fichier.');

resumes = [];
noms_resultats = {};
materiaux = {};
details_tout = {};

for numero = 1:numel(fichiers)
    nom_fichier = char(fichiers{numero});
    if ~isfile(nom_fichier)
        fprintf('Fichier absent, analyse ignoree : %s\n',nom_fichier);
        continue
    end
    S = load(nom_fichier);
    st = resolution_contraste(S);
    n = st.n_impacts;
    n_cols = ceil(sqrt(n));
    n_rows = ceil(n/n_cols);

    figure('Name',[st.nom_forme ' - profils'],'Color','w', ...
        'Position',[80 80 1550 1100]);
    disposition_profils = tiledlayout(n_rows,n_cols,'TileSpacing','loose','Padding','loose');
    for p = 1:n
        ax = nexttile(disposition_profils);
        plot(ax,st.absc_x{p},st.courbe_x{p},'-','LineWidth',2,'Color',[0.10 0.35 0.70]);
        hold(ax,'on');
        plot(ax,st.absc_y{p},st.courbe_y{p},'-','LineWidth',2,'Color',[0.85 0.35 0.10]);
        if isfinite(st.seuil_x(p)), yline(ax,st.seuil_x(p),'--','Color',[0.4 0.4 0.4]); end
        xline(ax,0,':','Color',[0.5 0.5 0.5]);
        grid(ax,'on');
        if p > n-n_cols, xlabel(ax,'Deplacement [cm]'); end
        if mod(p-1,n_cols)==0, ylabel(ax,'Correlation maximale'); end
        title(ax,{sprintf('Impact %d',p), ...
            sprintf('Rx = %.2f cm | Ry = %.2f cm',st.Rx(p),st.Ry(p))},'FontSize',11);
        if ~isempty(st.absc_x{p})
            limite = max([abs(st.absc_x{p}); abs(st.absc_y{p}); 1]);
            xlim(ax,[-limite limite]);
        end
        ylim(ax,[0 1.05]);
        set(ax,'FontSize',10);
    end
    title(disposition_profils,{[st.nom_forme ' / ' st.materiau ' : profils de correlation'], ...
        sprintf('N = %d impacts   |   Bleu : x   |   Orange : y   |   Tirets : mi-hauteur',n)});

    figure('Name',[st.nom_forme ' - grille'],'Color','w', ...
        'Position',[100 100 1500 1050]);
    disposition_carte = tiledlayout(n_rows,n_cols,'TileSpacing','loose','Padding','loose');
    y_cm = S.impacts(:,2)*S.dy*100;
    x_cm = S.impacts(:,1)*S.dx*100;
    marge_y = max(1,0.15*(max(y_cm)-min(y_cm)));
    marge_x = max(1,0.15*(max(x_cm)-min(x_cm)));
    for p = 1:n
        ax = nexttile(disposition_carte);
        autres = setdiff(1:n,p);
        scatter(ax,y_cm(autres),x_cm(autres),115,st.couleurs(p,autres), ...
            'filled','MarkerEdgeColor','w','LineWidth',0.8);
        hold(ax,'on');
        plot(ax,y_cm(p),x_cm(p),'o','MarkerSize',12, ...
            'MarkerFaceColor','w','MarkerEdgeColor','k','LineWidth',2);
        grid(ax,'on'); axis(ax,'equal');
        xlim(ax,[min(y_cm)-marge_y max(y_cm)+marge_y]);
        ylim(ax,[min(x_cm)-marge_x max(x_cm)+marge_x]);
        set(ax,'YDir','reverse');
        caxis(ax,[0 1]);
        if p > n-n_cols, xlabel(ax,'Position y [cm]'); end
        if mod(p-1,n_cols)==0, ylabel(ax,'Position x [cm]'); end
        title(ax,{sprintf('Impact %d',p), ...
            sprintf('Autre max : %.2f',st.confusion_max(p))},'FontSize',11);
        set(ax,'FontSize',10);
    end
    colormap(gcf,parula(256));
    barre = colorbar(ax,'southoutside');
    barre.Layout.Tile = 'south';
    barre.Label.String = 'Correlation maximale normalisee (0 a 1)';
    title(disposition_carte,{sprintf('%s : ressemblance entre les %d impacts',st.nom_forme,n), ...
        'Cercle blanc : reference   |   Echelle fixe de 0 a 1'});

    fprintf('\n%s  [%s]  (N = %d impacts)\n',st.nom_forme,st.materiau,n);
    fprintf('Impact | R x [cm] | R y [cm] | C profil | C grille | Autre max\n');
    for p = 1:n
        fprintf('%6d | %8.2f | %8.2f | %8.2f | %8.2f | %9.2f\n', ...
            p,st.Rx(p),st.Ry(p),st.contraste_profil(p), ...
            st.contraste_grille(p),st.confusion_max(p));
    end
    afficherResume('Rx [cm]',st.agg.Rx);
    afficherResume('Ry [cm]',st.agg.Ry);
    afficherResume('Contraste profil',st.agg.contraste_profil);
    afficherResume('Contraste grille',st.agg.contraste_grille);
    fprintf('Pire ressemblance avec un autre impact : %.2f\n',max(st.confusion_max));

    details = table((1:9)',st.Rx,st.Ry,st.contraste_profil,st.contraste_grille,st.confusion_max, ...
        'VariableNames',{'Impact','Rx_cm','Ry_cm','Contraste_profil','Contraste_grille','Autre_max'});
    [dossier_entree,base_entree] = fileparts(nom_fichier);
    writetable(details,fullfile(dossier_entree,[base_entree '_analyse.csv']));
    details_tout{end+1} = details; %#ok<AGROW>

    noms_resultats{end+1} = st.nom_forme; %#ok<AGROW>
    materiaux{end+1} = st.materiau; %#ok<AGROW>
    resumes = [resumes; ...
        st.agg.Rx.moy, st.agg.Rx.min, st.agg.Rx.max, st.agg.Rx.ecart_type, st.agg.Rx.incertitude, ...
        st.agg.Ry.moy, st.agg.Ry.min, st.agg.Ry.max, st.agg.Ry.ecart_type, st.agg.Ry.incertitude, ...
        st.agg.contraste_profil.moy, st.agg.contraste_profil.ecart_type, ...
        st.agg.contraste_grille.moy, st.agg.contraste_grille.min, ...
        st.agg.contraste_grille.max, max(st.confusion_max)]; %#ok<AGROW>
end

if isempty(resumes)
    synthese = table();
    fprintf('Aucun fichier analyse.\n');
    return
end

synthese = array2table(resumes,'VariableNames', ...
    {'Rx_moy_cm','Rx_min_cm','Rx_max_cm','Rx_std_cm','Rx_inc_cm', ...
     'Ry_moy_cm','Ry_min_cm','Ry_max_cm','Ry_std_cm','Ry_inc_cm', ...
     'Cp_moy','Cp_std','Cg_moy','Cg_min','Cg_max','Autre_max'});
synthese = addvars(synthese,string(materiaux(:)), ...
    'Before',1,'NewVariableNames','Materiau');
synthese = addvars(synthese,string(noms_resultats(:)), ...
    'Before',1,'NewVariableNames','Forme');
fprintf('\nSYNTHESE DES FORMES ANALYSEES (moy +/- incertitude type)\n');
disp(synthese);
fprintf('Rx et Ry : largeur a mi-hauteur depuis la ligne de base (manuel 3.5).\n');
fprintf('Petits Rx et Ry souhaitables ; pas une separation garantie entre notes.\n');
fprintf('Cp = Cmax / ligne de base. Cg = 1 / moyenne des 8 autres impacts.\n');
fprintf('std : dispersion entre les 9 impacts. inc = std/sqrt(N).\n');
fprintf('Simulation acoustique 2D : ne modelise pas la flexion d une vraie plaque.\n');
if ~isfolder(dossier_resultats), mkdir(dossier_resultats); end
writetable(synthese,fullfile(dossier_resultats,'Synthese_formes.csv'));
end

function afficherResume(nom,agg)
if ~isfinite(agg.moy)
    fprintf('%s : indetermine (aucun pic mesurable).\n',nom);
    return
end
fprintf(['%s : moyenne %.2f +/- %.2f (std %.2f) | min %.2f | max %.2f ' ...
    '| N = %d/%d\n'],nom,agg.moy,agg.incertitude,agg.ecart_type, ...
    agg.min,agg.max,agg.n_valides,agg.n_total);
end
