"""RoboFab for Glyphs"""
# -*- coding: utf-8 -*-
import sys
import objc
from GlyphsApp import *

from AppKit import *
from Foundation import *

from robofab import RoboFabError, RoboFabWarning, ufoLib
from robofab.objects.objectsBase import BaseFont, BaseKerning, BaseGroups, BaseInfo, BaseFeatures, BaseLib,\
		BaseGlyph, BaseContour, BaseSegment, BasePoint, BaseBPoint, BaseAnchor, BaseGuide, BaseComponent, \
		relativeBCPIn, relativeBCPOut, absoluteBCPIn, absoluteBCPOut, _box,\
		_interpolate, _interpolatePt, roundPt, addPt,\
		MOVE, LINE, CORNER, CURVE, QCURVE, OFFCURVE,\
		BasePostScriptFontHintValues, postScriptHintDataLibKey, BasePostScriptGlyphHintValues

import os
from warnings import warn

__all__ = ["CurrentFont", "CurrentGlyph", 'OpenFont', 'RFont', 'RGlyph', 'RContour', 'RPoint', 'RAnchor', 'RComponent', "NewFont"]

GSMOVE = 17
GSLINE = 1
GSCURVE = 35
GSOFFCURVE = 65
GSSHARP = 0
GSSMOOTH = 4096

LOCAL_ENCODING = "macroman"

# This is for compatibility until the proper implementaion is shipped.
if type(GSElement.parent) != type(GSGlyph.parent):
	GSElement.parent = property(lambda self: self.valueForKey_("parent"))


def CurrentFont():
	"""Return a RoboFab font object for the currently selected font."""
	if Glyphs.currentDocument:
		try:
			return RFont( Glyphs.currentDocument, Glyphs.currentDocument.windowControllers()[0].masterIndex() )
		except:
			pass
	return None

def AllFonts():
	"""Return a list of all open fonts."""
	fontCount = len(Glyphs.documents)
	all = []
	for doc in Glyphs.documents:
		all.append(RFont(doc, doc.windowController().masterIndex()))
	return all


def CurrentGlyph():
	"""Return a RoboFab glyph object for the currently selected glyph."""
	Doc = Glyphs.currentDocument
	try:
		Layer = Doc.selectedLayers()[0]
		return RGlyph(Layer.parent)
	except: pass
	
	print "No glyph selected!"
	return None

def OpenFont(path=None, note=None):
	"""Open a font from a path."""
	if path == None:
		#from robofab.interface.all.dialogs import GetFile
		path = GetFile(note, filetypes=["ufo", "glyphs", "otf", "ttf"])
	if path:
		if path[-7:].lower() == '.glyphs' or path[-3:].lower() in ["ufo", "otf", "ttf"]:
			doc = Glyphs.openDocumentWithContentsOfFile_display_(path, False) #chrashed !!
			if doc != None:
				return RFont(doc)
	return None

def NewFont(familyName=None, styleName=None):
	"""Make a new font"""
	doc = Glyphs.documentController().openUntitledDocumentAndDisplay_error_(True, None)
	rf = RFont(doc)
	if familyName:
		rf.info.familyName = familyName
	if styleName:
		rf.info.styleName = styleName
	return rf

class PostScriptFontHintValues(BasePostScriptFontHintValues):
	"""	Font level PostScript hints object for objectsRF usage.
		If there are values in the lib, use those.
		If there are no values in the lib, use defaults.
		
		The psHints attribute for objectsRF.RFont is basically just the
		data read from the Lib. When the object saves to UFO, the 
		hints are written back to the lib, which is then saved.
	"""
	
	def __init__(self, aFont=None, data=None):
		self.setParent(aFont)
		BasePostScriptFontHintValues.__init__(self)
		if aFont is not None:
			# in version 1, this data was stored in the lib
			# if it is still there, guess that it is correct
			# move it to font info and remove it from the lib.
			libData = aFont.lib.get(postScriptHintDataLibKey)
			if libData is not None:
				self.fromDict(libData)
				del libData[postScriptHintDataLibKey]
		if data is not None:
			self.fromDict(data)

def getPostScriptHintDataFromLib(aFont, fontLib):
	hintData = fontLib.get(postScriptHintDataLibKey)
	psh = PostScriptFontHintValues(aFont)
	psh.fromDict(hintData)
	return psh
	
class PostScriptGlyphHintValues(BasePostScriptGlyphHintValues):
	"""	Glyph level PostScript hints object for objectsRF usage.
		If there are values in the lib, use those.
		If there are no values in the lib, be empty.
	"""
	def __init__(self, aGlyph=None, data=None):
		# read the data from the glyph.lib, it won't be anywhere else
		BasePostScriptGlyphHintValues.__init__(self)
		if aGlyph is not None:
			self.setParent(aGlyph)
			self._loadFromLib(aGlyph.lib)
		if data is not None:
			self.fromDict(data)
	
	
class RFont(BaseFont):
	"""RoboFab UFO wrapper for GS Font object"""
	
	_title = "GSFont"
	
	def __init__(self, doc=None, master=0):
		BaseFont.__init__(self)
		if doc is None:
			doc = Glyphs.documentController().openUntitledDocumentAndDisplay_error_(True, None)
		
		if type(doc) == type(()):
			doc = doc[0]
		self._object = doc
		self._master = master
		self._masterKey = doc.font.masters[master].id
		self.features = RFeatures(doc.font)
		self._lib = {}
		self.info = RInfo(self)
		
		self._supportHints = False
		self._RGlyphs = {}
	
	def keys(self):
		keys = {}
		for glyph in self._object.font.glyphs:
			glyphName = glyph.name
			if glyphName in keys:
				n = 1
				while ("%s#%s" % (glyphName, n)) in keys:
					n += 1
				newGlyphName = "%s#%s" % (glyphName, n)
				print "RoboFab encountered a duplicate glyph name, renaming %r to %r" % (glyphName, newGlyphName)
				glyphName = newGlyphName
				glyph.setName_(glyphName)
			keys[glyphName] = None
		return keys.keys()

	def has_key(self, glyphName):
		glyph = self._object.font.glyphForName_(glyphName)
		if glyph is None:
			return False
		else:
			return True
	
	__contains__ = has_key
	
	def __setitem__(self, glyphName, glyph):
		self._object.font.addGlyph_( glyph.naked() )
	
	def __getitem__(self, glyphName):
		GGlyph = self._object.font.glyphForName_(glyphName)
		if GGlyph is None:
			raise KeyError("Glyph '%s' not in font." % glyphName)
		else:
			glyph = RGlyph(GGlyph, self._master)
			glyph.setParent(self)
			return glyph
	
	def __cmp__(self, other):
		if not hasattr(other, '_object'):
			return -1
		return self._compare(other)
		if self._object.fileName() == other._object.fileName():
			# so, names match.
			# this will falsely identify two distinct "Untitled"
			# let's check some more
			return 0
		else:
			return -1
	
	def __len__(self):
		if self._object.font.glyphs is None:
			return 0
		return len(self._object.font.glyphs)
	
	def close(self):
		self._object.close()
	
	def _get_lib(self):
		return self._object.font.userData.objectForKey_("org.robofab.ufoLib")
	
	def _set_lib(self, obj):
		self._object.font.userData.setObject_forKey_(obj, "org.robofab.ufoLib")
	
	lib = property(_get_lib, _set_lib, doc="font lib object")
	
	def _hasNotChanged(self, doGlyphs=True):
		raise NotImplementedError
	
	def _get_path(self):
		return self._object.fileURL().path()
	
	path = property(_get_path, doc="path of the font")
	
	def _get_groups(self):
		Dictionary = {}
		for currGlyph in self._object.font.glyphs:
			if currGlyph.leftKerningGroupId():
				Group = Dictionary.get(currGlyph.leftKerningGroupId(), None)
				if not Group:
					Group = []
					Dictionary[currGlyph.leftKerningGroupId()] = Group
				Group.append(currGlyph.name)
			if currGlyph.rightKerningGroupId():
				Group = Dictionary.get(currGlyph.rightKerningGroupId(), None)
				if not Group:
					Group = []
					Dictionary[currGlyph.rightKerningGroupId()] = Group
				Group.append(currGlyph.name)
		for aClass in self._object.font.classes:
			Dictionary[aClass.name] = aClass.code.split(" ")
		return Dictionary
	
	def _set_groups(self, GroupsDict):
		for currGroupKey in GroupsDict.keys():
			if currGroupKey.startswith("@MMK_L_"):
				Group = GroupsDict[currGroupKey]
				if Group:
					for GlyphName in Group:
						if ChangedGlyphNames.has_key(currGroupKey):
							currGroupKey = ChangedGlyphNames[currGroupKey]
						if ChangedGlyphNames.has_key(GlyphName): 
							GlyphName = ChangedGlyphNames[GlyphName]
						self._object.font.glyphForName_(GlyphName).setRightKerningGroupId_( currGroupKey )
			
			elif currGroupKey.startswith("@MMK_R_"):
				Group = GroupsDict[currGroupKey]
				if Group:
					for GlyphName in Group:
						self._object.font.glyphForName_(GlyphName).setLeftKerningGroupId_(currGroupKey)
			else:
				newClass = GSClass()
				newClass.setName_( currGroupKey )
				newClass.setCode_( " ".join(GroupsDict[currGroupKey]))
				newClass.setAutomatic_( False )
				self._object.font.addClass_(newClass)
	
	groups = property(_get_groups, _set_groups, doc="groups")
	
	def _get_kerning(self):
		FontMaster = self._object.font.masters[self._master]
		GSKerning = self._object.font.kerning.objectForKey_(FontMaster.id)
		kerning = {}
		if GSKerning != None:
			for LeftKey in GSKerning.allKeys():
				LeftKerning = GSKerning.objectForKey_(LeftKey)
				if LeftKey[0] != '@':
					LeftKey = self._object.font.glyphForId_(LeftKey).name
				for RightKey in LeftKerning.allKeys():
					RightKerning = LeftKerning.objectForKey_(RightKey)
					if RightKey[0] != '@':
						RightKey = self._object.font.glyphForId_(RightKey).name
					kerning[(LeftKey, RightKey)] = RightKerning
		rk = RKerning(kerning)
		rk.setParent(self)
		return rk
	
	def _set_kerning(self, kerning):
		FontMasterID = self._object.font.masters[self._master].id
		LeftKerning = NSMutableDictionary.alloc().init()
		Font = self._object.font
		for pair in kerning:
			Font.setKerningForFontMasterID_LeftKey_RightKey_Value_(FontMasterID, pair[0], pair[1], kerning[pair])
	
	kerning = property(_get_kerning, _set_kerning, doc="groups")
	
	#
	# methods for imitating GlyphSet?
	#
	
	def getWidth(self, glyphName):
		if self._object.font.glyphForName_(glyphName):
			return self._object.font.glyphForName_(glyphName).layerForKey_(self._masterKey).width()
		raise IndexError		# or return None?
	
	def save(self, path=None):
		"""Save the font, path is required."""
		if not path:
			if not self._object.filePath():
				raise RoboFabError, "No destination path specified."
			else:
				self._object.setFilePath_( self.filename )
		else:
			self._object.setFilePath_( path )
		self._object.saveDocument_(None)
	
	def close(self, save=False):
		"""Close the font, saving is optional."""
		if save:
			self.save()
		else:
			self._object.updateChangeCount_(NSChangeCleared)
		self._object.close()
	
	def _get_glyphOrder(self):
		return self._object.font.valueForKeyPath_("glyphs.name")
	
	glyphOrder = property(_get_glyphOrder, doc="groups")
	
	def getGlyph(self, glyphName):
		# XXX getGlyph may have to become private, to avoid duplication
		# with __getitem__
		n = None
		if self._RGlyphs.has_key(glyphName):
			# have we served this glyph before? it should be in _object
			n = self._RGlyphs[glyphName]
		else:
			# haven't served it before, is it in the glyphSet then?
			n = RGlyph( self._object.font.glyphForName_(glyphName) )
			self._RGlyphs[glyphName] = n
			
		if n is None:
			raise KeyError, glyphName
		return n
	
	def newGlyph(self, glyphName, clear=True):
		"""Make a new glyph"""
		g = self._object.font.glyphForName_(glyphName)
		if g is None:
			g = GSGlyph(glyphName)
			self._object.font.addGlyph_(g)
		elif clear:
			g.layers[self._masterKey] = GSLayer()
		return self[glyphName]
	
	def insertGlyph(self, glyph, newGlyphName=None):
		"""returns a new glyph that has been inserted into the font"""
		if newGlyphName is None:
			name = glyph.name
		else:
			name = newGlyphName
		glyph = glyph.copy()
		glyph.name = name
		glyph.setParent(self)
		glyph._hasChanged()
		self._RGlyphs[name] = glyph
		# is the user adding a glyph that has the same
		# name as one that was deleted earlier?
		#if name in self._scheduledForDeletion:
		#	self._scheduledForDeletion.remove(name)
		return self.getGlyph(name)
		
	def removeGlyph(self, glyphName):
		"""remove a glyph from the font"""
		# XXX! Potential issue with removing glyphs.
		# if a glyph is removed from a font, but it is still referenced
		# by a component, it will give pens some trouble.
		# where does the resposibility for catching this fall?
		# the removeGlyph method? the addComponent method
		# of the various pens? somewhere else? hm... tricky.
		#
		# we won't actually remove it, we will just store it for removal
		# but only if the glyph does exist
		# if self.has_key(glyphName) and glyphName not in self._scheduledForDeletion:
		# 	self._scheduledForDeletion.append(glyphName)
		# now delete the object
		if glyphName in self._object.font.glyphs:
			del self._object.font[glyphName]
		self._hasChanged()
	
	def _get_selection(self):
		"""return a list of glyph names for glyphs selected in the font window """
		l=[]
		for Layer in self._object.selectedLayers():
			l.append(Layer.parent.name)
		return l
	
	def _set_selection(self, list):
		raise NotImplementedError
		return
	
	selection = property(_get_selection, _set_selection, doc="list of selected glyph names")

class RGlyph(BaseGlyph):
	
	_title = "GSGlyph"
	
	def __init__(self, _GSGlyph = None, master = 0):
		if _GSGlyph is None:
			_GSGlyph = GSGlyph()
		
		self._object = _GSGlyph
		self._layerID = None
		try:
			if _GSGlyph.parent:
				self._layerID = _GSGlyph.parent.masters[master].id
			elif (_GSGlyph.layers[master]):
				self._layerID = _GSGlyph.layers[master].layerId
		except:
			pass
		self.masterIndex = master
		if self._layerID:
			self._layer = _GSGlyph.layerForKey_(self._layerID)
		else:
			self._layerID = "undefined"
			self._layer = GSLayer()
			_GSGlyph.setLayer_forKey_(self._layer, self._layerID)
		self._contours = None
		
	def __repr__(self):
		font = "unnamed_font"
		glyph = "unnamed_glyph"
		fontParent = self.getParent()
		if fontParent is not None:
			try:
				font = fontParent.info.postscriptFullName
			except AttributeError:
				pass
		try:
			glyph = self.name
		except AttributeError:
			pass
		return "<RGlyph %s for %s.%s>" %(self._object.name, font, glyph)
	
	def __getitem__(self, index):
		return self.contours[index]
	
	def __delitem__(self, index):
		self._layer.removePathAtIndex_(index)
		self._invalidateContours()
	
	def __len__(self):
		return len(self.contours)
	
	def _invalidateContours(self):
		self._contours = None
	
	def _buildContours(self):
		self._contours = []
		for currPath in self._layer.paths:
			c = RContour(currPath)
			c.setParent(self)
			#c._buildSegments()
			self._contours.append(c)
	
	def __len__(self):
		return len(self._layer.paths)
	
	def copy(self):
		Copy = RGlyph(self._object.copy(), self.masterIndex)
		Copy._layerID = self._layerID
		Copy._layer = Copy._object.layerForKey_(self._layerID)
		return Copy
	
	def _get_contours(self):
		if self._contours is None:
			self._buildContours()
		return self._contours
	
	contours = property(_get_contours, doc="allow for iteration through glyph.contours")
	
	def _hasNotChanged(self):
		raise NotImplementedError
	
	def _get_box(self):
		bounds = self._layer.bounds
		bounds = (int(round(NSMinX(bounds))), int(round(NSMinY(bounds))), int(round(NSMaxX(bounds))), int(round(NSMaxY(bounds))))
		return bounds
	
	box = property(_get_box, doc="the bounding box of the glyph: (xMin, yMin, xMax, yMax)")
	
	#
	# attributes
	#
	
	def _get_lib(self):
		try:
			return self._object.userData()
		except:
			return None
	
	def _set_lib(self, key, obj):
		if self._object.userData() is objc.nil:
			self._object.setUserData_(NSMutableDictionary.dictionary())
		self._object.userData().setObject_forKey_(obj, key)
		
	lib = property(_get_lib, _set_lib, doc="Glyph Lib")
	
	def _get_name(self):
		return self._object.name
	
	def _set_name(self, newName):
		prevName = self.name
		if newName == prevName:
			return
		self._object.name = newName
	
	name = property(_get_name, _set_name)
	
	def _get_unicodes(self):
		if self._object.unicode is not None:
			return [int(self._object.unicode, 16)]
		return []
	
	def _set_unicodes(self, value):
		if not isinstance(value, list):
			raise RoboFabError, "unicodes must be a list"
		try:
			self._object.setUnicode = value[0]
		except:
			pass
	
	unicodes = property(_get_unicodes, _set_unicodes, doc="all unicode values for the glyph")
	
	def _get_unicode(self):
		if self._object.unicode is None:
			return None
		return self._object.unicodeChar()
	
	def _set_unicode(self, value):
		if type(value) == str:
			if value is not None and value is not self._object.unicode:
				self._object.setUnicode_(value)
		elif type(value) == int:
			strValue = "%0.4X" % value
			if strValue is not None and strValue is not self._object.unicode:
				self._object.setUnicode_(strValue)
		else:
			raise(KeyError)
	
	unicode = property(_get_unicode, _set_unicode, doc="first unicode value for the glyph")
	
	index =  property(lambda self: self._object.parent.indexOfGlyph_(self._object))
	
	note = property(lambda self: self._object.valueForKey_("note"),
					lambda self, value: self._object.setNote_(value))
	
	
	def _get_leftMargin(self):
		return self._layer.LSB

	def _set_leftMargin(self, value):
		self._layer.setLSB_(value)
	
	leftMargin = property(_get_leftMargin, _set_leftMargin, doc="Left Side Bearing")
		
	def _get_rightMargin(self):
		return self._layer.RSB
	
	def _set_rightMargin(self, value):
		self._layer.setRSB_(value)
	
	rightMargin = property(_get_rightMargin, _set_rightMargin, doc="Right Side Bearing")
	
	def _get_width(self):
		return self._layer.width
	
	def _set_width(self, value):
		self._layer.setWidth_(value)
	
	width = property(_get_width, _set_width, doc="width")
	
	def getComponents(self):
		Components = []
		for c in self._layer.components:
			T = c.transformStruct()
			Components.append(RComponent( baseGlyphName=c.componentName, offset=(T[4], T[5]), scale=(T[0], T[3])))
		return Components
	
	components = property(getComponents, doc="List of components")
	
	def getAnchors(self):
		return self.anchors
	
	def getPointPen(self):
		if "GSPen" in sys.modules.keys():
			del(sys.modules["GSPen"])
		from GSPen import GSPointPen
		
		return GSPointPen(self, self._layer)

	def appendComponent(self, baseGlyph, offset=(0, 0), scale=(1, 1)):
		"""append a component to the glyph"""
		new = GSComponent(baseGlyph, offset, scale)
		self._layer.addComponent_(new)
	
	def appendAnchor(self, name, position, mark=None):
		"""append an anchor to the glyph"""
		new = GSAnchor(name=name, pt=position )
		#new.setParent(self)
		self._layer.addAnchor_(new)
	
	def removeContour(self, index):
		"""remove  a specific contour from the glyph"""
		self._layer.removePathAtIndex_(index)
	
	def removeAnchor(self, anchor):
		"""remove  a specific anchor from the glyph"""
		self._layer.removeAnchor_(anchor)
	
	def removeComponent(self, component):
		"""remove  a specific component from the glyph"""
		self._layer.removeComponent_(component)
	
	def center(self, padding=None):
		"""Equalise sidebearings, set to padding if wanted."""
		left = self._layer.LSB
		right = self._layer.RSB
		if padding:
			e_left = e_right = padding
		else:
			e_left = (left + right)/2
			e_right = (left + right) - e_left
		self._layer.setLSB_(e_left)
		self._layer.setRSB_(e_right)
	
	def decompose(self):
		"""Decompose all components"""
		self._layer.decomposeComponents()
	
	def clear(self, contours=True, components=True, anchors=True, guides=True):
		"""Clear all items marked as True from the glyph"""
		if contours:
			self.clearContours()
		if components:
			self.clearComponents()
		if anchors:
			self.clearAnchors()
		if guides:
			self.clearHGuides()
			self.clearVGuides()
	
	def clearContours(self):
		"""clear all contours"""
		while len(self._layer.paths) > 0:
			self._layer.removePathAtIndex_(0)
	
	def clearComponents(self):
		"""clear all components"""
		self._layer.setComponents_(NSMutableArray.array())
	
	def clearAnchors(self):
		"""clear all anchors"""
		self._layer.setAnchors_(NSMutableDictionary.dictionary())
		
	def clearHGuides(self):
		"""clear all horizontal guides"""
		#raise NotImplementedError
		pass
		# self.hGuides = []
		# self._hasChanged()
	
	def clearVGuides(self):
		"""clear all vertical guides"""
		#raise NotImplementedError
		pass
		# self.vGuides = []
		# self._hasChanged()
	
	def update(self):
		self._contours = None
		GSGlyphsInfo.updateGlyphInfo_changeName_(self._object, False)
	
	def correctDirection(self, trueType=False):
		self._layer.correctPathDirection()
	
	def removeOverlap(self):
		removeOverlapFilter = NSClassFromString("GlyphsFilterRemoveOverlap").alloc().init()
		removeOverlapFilter.runFilterWithLayer_error_(self._layer, None)
		
	def _mathCopy(self):
		""" copy self without contour, component and anchor data """
		glyph = self._getMathDestination()
		glyph.name = self.name
		glyph.unicodes = list(self.unicodes)
		glyph.width = self.width
		glyph.note = self.note
		try:
			glyph.lib = dict(self.lib)
		except:
			pass
		return glyph

class RGlyphAnchorsProxy (object):
	def __init__(self, Layer):
		self._owner = Layer
	def __getitem__(self, Key):
		Anchor = self._owner.anchors[Key]
		if Anchor is not None:
			return RAnchor(Anchor)
	def __setitem__(self, Key, Anchor):
		if type(Key) is str:
			Anchor.setName_(Key)
			self._owner.addAnchor_(Anchor)
		else:
			raise TypeError
	def __delitem__(self, Key):
		if type(Key) is str:
			self._owner.removeAnchorWithName_(Key)
		else:
			raise TypeError
	def __iter__(self):
		if self._owner.anchorCount() > 0:
			for Anchor in self._owner.pyobjc_instanceMethods.anchors().allValues():
				yield RAnchor(Anchor)
	def append(self, Anchor):
		self._owner.addAnchor_(Anchor)
	def __len__(self):
		return self._owner.anchorCount()
	def __str__(self):
		StringVal = "(\n"
		for key in self._owner.pyobjc_instanceMethods.anchors().allKeys():
			currAnchor = self._owner.anchorForName_(key)
			StringVal += "	%s {%.0f, %.0f},\n" % (currAnchor.name, currAnchor.position.x, currAnchor.position.y)
		StringVal += ")"
		return StringVal

RGlyph.anchors = property(lambda self: RGlyphAnchorsProxy(self._layer))


class RContour(BaseContour):
	
	_title = "GSContour"
	
	def __init__(self, object=None):
		#BaseContour.__init__(self)
		self._object  = object #GSPath
	
	def __repr__(self):
		return "<RContour with %d nodes>"%(len(self._object.nodes))
	def __len__(self):
		return len(self._object.nodes)
	
	def __getitem__(self, index):
		if index < len(self.segments):
			return self.segments[index]
		raise IndexError
	
	def _get_index(self):
		return self.getParent().contours.index(self)
	
	def _set_index(self, index):
		ogIndex = self.index
		if index != ogIndex:
			contourList = self.getParent().contours
			contourList.insert(index, contourList.pop(ogIndex))
	
	index = property(_get_index, _set_index, doc="index of the contour")
	
	def _get_points(self):
		'''returns a list of RPoints, generated on demand from the GSPath.nodes'''
		points = []
		Node = None
		for Node in self._object.nodes:
			Type = MOVE
			if Node.type == GSLINE:
				Type = LINE
			elif Node.type == GSCURVE:
				Type = CURVE
			elif Node.type == GSOFFCURVE:
				Type = OFFCURVE
			X = Node.position.x
			Y = Node.position.y
			_RPoint = RPoint(Node)
			_RPoint.parent = self
			_RPoint.smooth = Node.connection == GSSMOOTH
			
			points.append(_RPoint) #x=0, y=0, pointType=None, name=None):
		
		if not self._object.closed:
			points[0].type = MOVE
		
		return points
	
	def _set_points(self, points):
		'''first makes sure that the GSPath.nodes has the right length, than sets the properties from points to nodes'''
		while len(points) > self._object.nodes().count():
			newNode = GSNode()
			self._object.addNode_(newNode)
		while len(points) < self._object.nodes().count():
			self._object.removeNodeAtIndex_( 0 )
		#assert(len(points) == self._object.nodes().count(), "The new point list and the path.nodes count should be equal")
		for i in range(len(points)):
			Node = self._object.nodeAtIndex_(i)
			Node.setPosition_((points[i].x, points[i].y))
			if points[i].type == MOVE:
				Node.setType_( GSLINE )
				self._object.setClosed_(False)
			if points[i].type == LINE:
				Node.setType_( GSLINE )
			if points[i].type == CURVE:
				Node.setType_( GSCURVE )
			if points[i].type == OFFCURVE:
				Node.setType_( GSOFFCURVE )
			if points[i].smooth:
				Node.setConnection_( GSSMOOTH )
			else:
				Node.setConnection_( GSSHARP )
	
	points = property(_get_points, _set_points, doc="the contour as a list of points")
	
	def _get_bPoints(self):
		bPoints = []
		for segment in self.segments:
			segType = segment.type
			if segType == MOVE or segType == LINE or segType == CURVE:
				b = RBPoint(segment)
				bPoints.append(b)
			else:
				raise RoboFabError, "encountered unknown segment type"
		return bPoints
	
	bPoints = property(_get_bPoints, doc="view the contour as a list of bPoints")
	
	def draw(self, pen):
		"""draw the object with a fontTools pen"""
		
		if self._object.closed:
			for i in range(len(self), -1, -1):
				StartNode = self._object.nodeAtIndex_(i)
				if StartNode.type != GSOFFCURVE:
					pen.moveTo(StartNode.position)
					break
		else:
			for i in range(len(self)):
				StartNode = self._object.nodeAtIndex_(i)
				if StartNode.type != GSOFFCURVE:
					pen.moveTo(StartNode.position)
					break
		for i in range(len(self)):
			Node = self._object.nodeAtIndex_(i)
			if Node.type == GSLINE:
				pen.lineTo(Node.position)
			elif Node.type == GSCURVE:
				pen.curveTo(self._object.nodeAtIndex_(i-2).position, self._object.nodeAtIndex_(i-1).position, Node.position)
		if self._object.closed:
			pen.closePath()
		else:
			pen.endPath()
		
	def _get_segments(self):
		if not len(self._object.nodes):
			return []
		segments = []
		index = 0
		node = None
		for i in range(len(self._object.nodes)):
			node = self._object.nodeAtIndex_(i)
			if node.type == GSLINE or node.type == GSCURVE:
				_Segment = RSegment(index, self, node)
				_Segment.parent = self
				_Segment.index = index
				segments.append(_Segment)
				index += 1
		if self._object.closed:
			# TODO fix this out properly. 
			# _Segment = RSegment(0, self, node)
			# _Segment.type = MOVE
			# segments.insert(0, _Segment)
			pass
		else:
			_Segment = RSegment(0, self, self._object.nodeAtIndex_(0))
			_Segment.type = MOVE
			segments.insert(0, _Segment)
			
		return segments
	
	def _set_segments(self, segments):
		points = []
		for segment in segments:
			points.append(segment.points)
		
	segments = property(_get_segments, _set_segments, doc="A list of all points in the contour organized into segments.")
	
	
	def appendSegment(self, segmentType, points, smooth=False):
		"""append a segment to the contour"""
		segment = self.insertSegment(index=len(self.segments), segmentType=segmentType, points=points, smooth=smooth)
		return segment
		
	def insertSegment(self, index, segmentType, points, smooth=False):
		"""insert a segment into the contour"""
		segment = RSegment(index, points, smooth)
		segment.setParent(self)
		self.segments.insert(index, segment)
		self._hasChanged()
		return segment
		
	def removeSegment(self, index):
		"""remove a segment from the contour"""
		del self.segments[index]
		self._hasChanged()
	
	def reverseContour(self):
		"""reverse contour direction"""
		self._object.reverse()
	
	def setStartSegment(self, segmentIndex):
		"""set the first segment on the contour"""
		# this obviously does not support open contours
		if len(self.segments) < 2:
			return
		if segmentIndex == 0:
			return
		if segmentIndex > len(self.segments)-1:
			raise IndexError, 'segment index not in segments list'
		oldStart = self.segments[0]
		oldLast = self.segments[-1]
		 #check to see if the contour ended with a curve on top of the move
		 #if we find one delete it,
		if oldLast.type == CURVE or oldLast.type == QCURVE:
			startOn = oldStart.onCurve
			lastOn = oldLast.onCurve
			if startOn.x == lastOn.x and startOn.y == lastOn.y:
				del self.segments[0]
				# since we deleted the first contour, the segmentIndex needs to shift
				segmentIndex = segmentIndex - 1
		# if we DO have a move left over, we need to convert it to a line
		if self.segments[0].type == MOVE:
			self.segments[0].type = LINE
		# slice up the segments and reassign them to the contour
		segments = self.segments[segmentIndex:]
		self.segments = segments + self.segments[:segmentIndex]
		# now, draw the contour onto the parent glyph
		glyph = self.getParent()
		pen = glyph.getPointPen()
		self.drawPoints(pen)
		# we've drawn the new contour onto our parent glyph,
		# so it sits at the end of the contours list:
		newContour = glyph.contours.pop(-1)
		for segment in newContour.segments:
			segment.setParent(self)
		self.segments = newContour.segments
		self._hasChanged()
	
	def _get_selected(self):
		selected = 0
		nodes = self._object.nodes
		Layer = self._object.parent
		for node in nodes:
			if node in Layer.selection():
				selected = 1
				break
		return selected

	def _set_selected(self, value):
		if value == 1:
			self._nakedParent.SelectContour(self._index)
		else:
			Layer = self._object.parent
			if value:
				Layer.addObjectsFromArrayToSelection_(self._object.nodes)
			else:
				Layer.removeObjectsFromSelection_(self._object.pyobjc_instanceMethods.nodes())
	
	selected = property(_get_selected, _set_selected, doc="selection of the contour: 1-selected or 0-unselected")


class RSegment(BaseSegment):
	#def __init__(self, index, points=[], smooth = False):
	def __init__(self, index, contoure, node):
		BaseSegment.__init__(self)
		self._object = node
		self.parent = contoure
		self.index = index
		self.isMove = False # to store if the segment is a move segment
	
	def __repr__(self):
		return "<RSegment %s (%d), r>"%(self.type, self.smooth)#, self.points)
	def getParent(self):
		return self.parent
	
	def _get_type(self):
		if self.isMove: return MOVE
		nodeType = self._object.type
		if nodeType == GSLINE:
			return LINE
		elif nodeType == GSCURVE:
			return CURVE
		elif nodeType == GSOFFCURVE:
			return OFFCURVE
		return
	
	def _set_type(self, pointType):
		if pointType == MOVE:
			self.isMove = True
			return
		raise NotImplementedError
		return
		onCurve = self.points[-1]
		ocType = onCurve.type
		if ocType == pointType:
			return
		#we are converting a cubic line into a cubic curve
		if pointType == CURVE and ocType == LINE:
			onCurve.type = pointType
			parent = self.getParent()
			prev = parent._prevSegment(self.index)
			p1 = RPoint(prev.onCurve.x, prev.onCurve.y, pointType=OFFCURVE)
			p1.setParent(self)
			p2 = RPoint(onCurve.x, onCurve.y, pointType=OFFCURVE)
			p2.setParent(self)
			self.points.insert(0, p2)
			self.points.insert(0, p1)
		#we are converting a cubic move to a curve
		elif pointType == CURVE and ocType == MOVE:
			onCurve.type = pointType
			parent = self.getParent()
			prev = parent._prevSegment(self.index)
			p1 = RPoint(prev.onCurve.x, prev.onCurve.y, pointType=OFFCURVE)
			p1.setParent(self)
			p2 = RPoint(onCurve.x, onCurve.y, pointType=OFFCURVE)
			p2.setParent(self)
			self.points.insert(0, p2)
			self.points.insert(0, p1)
		#we are converting a quad curve to a cubic curve
		elif pointType == CURVE and ocType == QCURVE:
			onCurve.type == CURVE
		#we are converting a cubic curve into a cubic line
		elif pointType == LINE and ocType == CURVE:
			p = self.points.pop(-1)
			self.points = [p]
			onCurve.type = pointType
			self.smooth = False
		#we are converting a cubic move to a line
		elif pointType == LINE and ocType == MOVE:
			onCurve.type = pointType
		#we are converting a quad curve to a line:
		elif pointType == LINE and ocType == QCURVE:
			p = self.points.pop(-1)
			self.points = [p]
			onCurve.type = pointType
			self.smooth = False	
		# we are converting to a quad curve where just about anything is legal
		elif pointType == QCURVE:
			onCurve.type = pointType
		else:
			raise RoboFabError, 'unknown segment type'
			
	type = property(_get_type, _set_type, doc="type of the segment")
	
	def _get_smooth(self):
		return self._object.connection == GSSMOOTH
		
	def _set_smooth(self, smooth):
		raise NotImplementedError
		
	
	smooth = property(_get_smooth, _set_smooth, doc="smooth of the segment")
	
	def insertPoint(self, index, pointType, point):
		x, y = point
		p = RPoint(x, y, pointType=pointType)
		p.setParent(self)
		self.points.insert(index, p)
		self._hasChanged()
	
	def removePoint(self, index):
		del self.points[index]
		self._hasChanged()
		
	def _get_points(self):
		Path = self._object.parent
		index = Path.indexOfNode_(self._object)
		points = []
		if index < len(Path.nodes):
			if self._object.type == GSCURVE:
				points.append(RPoint(Path.nodes[index-2]))
				points.append(RPoint(Path.nodes[index-1]))
				points.append(RPoint(Path.nodes[index]))
			elif self._object.type == GSLINE:
				points.append(RPoint(Path.nodes[index]))
		return points
	
	points = property(_get_points, doc="index of the segment")

	def _get_selected(self):
		Path = self._object.parent
		index = Path.indexOfNode_(self._object)
		Layer = Path.parent
		
		if self._object.type == GSCURVE:
			return Path.nodes[index-2] in Layer.selection() or Path.nodes[index-1] in Layer.selection() or Path.nodes[index] in Layer.selection()
		elif self._object.type == GSLINE:
			return Path.nodes[index] in Layer.selection()
	
	def _set_selected(self, select):
		Path = self._object.parent
		index = Path.indexOfNode_(self._object)
		Layer = Path.parent
		
		if self._object.type == GSCURVE:
			if select:
				Layer.addObjectsFromArrayToSelection_([Path.nodes[index-2], Path.nodes[index-1], Path.nodes[index] ] )
			else:
				Layer.removeObjectsFromSelection_([Path.nodes[index-2], Path.nodes[index-1], Path.nodes[index] ] )
		elif self._object.type == GSLINE:
			if select:
				Layer.addSelection_( Path.nodes[index] )
			else:
				Layer.removeObjectFromSelection_( Path.nodes[index] )
	
	selected = property(_get_selected, _set_selected, doc="if segment is selected")

class RBPoint(BaseBPoint):
	
	_title = "GlyphsBPoint"
	
	def __init__(self, segment):
		self._object = segment;
	
	def __repr__(self):
		FontName = "unnamed_font"
		GlyphName = "unnamed_glyph"
		pathIndex = -1
		nodeIndex = -1
		Path = self._object._object.parent
		if Path is not None:
			try:
				nodeIndex = Path.indexOfNode_(self._object._object)
			except AttributeError: pass
			Layer = Path.parent
			if Layer is not None:
				try:
					pathIndex = Layer.indexOfPath_(Path)
				except AttributeError: pass
				Glyph = Layer.parent
				if Glyph is not None:
					try:
						GlyphName = Glyph.name
					except AttributeError: pass
					Font = Glyph.parent
					if Font is not None:
						#try:
						FontName = Font.valueForKey_("familyName")
						#except AttributeError: pass
		return "<RBPoint (%.1f, %.1f) for %s.%s[%d][%d]>"%( self._object._object.position.x, self._object._object.position.y, FontName, GlyphName, pathIndex, nodeIndex)
	
	def getParent(self):
		return self._object
	
	def _setAnchorChanged(self, value):
		self._anchorPoint.setChanged(value)
	
	def _setNextChanged(self, value):
		self._nextOnCurve.setChanged(value)	
		
	def _get__parentSegment(self):
		return self._object
		
	_parentSegment = property(_get__parentSegment, doc="")
	
	def _get__nextOnCurve(self):
		pSeg = self._parentSegment
		contour = pSeg.getParent()
		#could this potentially return an incorrect index? say, if two segments are exactly the same?
		return contour.segments[(contour.segments.index(pSeg) + 1) % len(contour.segments)]
	
	_nextOnCurve = property(_get__nextOnCurve, doc="")
	
	def _get_index(self):
		return self._parentSegment.index
	
	index = property(_get_index, doc="index of the bPoint on the contour")
	
	def _get_selected(self):
		Path = self._object._object.parent
		
		Layer = Path.parent
		return self._object._object in Layer.selection()
	
	def _set_selected(self, value):
		Path = self._object.parent
		Layer = Path.parent
		Layer.selection().addObject_(self._object)
		
	selected = property(_get_selected, _set_selected, doc="")
	

class RPoint(BasePoint):
	
	_title = "GlyphsPoint"
	
	def __init__(self, gs_point):
		self._object = gs_point;
		self.isMove = False
		# self.selected = False
		self._type = False
		# self._x = x
		# self._y = y
		# self._name = None
		# self._smooth = False
	
	def __repr__(self):
		FontName = "unnamed_font"
		GlyphName = "unnamed_glyph"
		pathIndex = -1
		nodeIndex = -1
		Path = self._object.parent
		if Path is not None:
			
			try:
				nodeIndex = Path.indexOfNode_(self._object)
			except AttributeError: pass
			Layer = Path.parent
			if Layer is not None:
				try:
					pathIndex = Layer.indexOfPath_(Path)
				except AttributeError: pass
				Glyph = Layer.parent
				if Glyph is not None:
					try:
						GlyphName = Glyph.name
					except AttributeError: pass
					Font = Glyph.parent
					if Font is not None:
						#try:
						FontName = Font.valueForKey_("familyName")
						#except AttributeError: pass
		Type = ""
		if self._type == MOVE:
			Type = "MOVE"
		elif self._object.type == GSOFFCURVE:
			Type ="OFFCURVE"
		elif self._object.type == GSCURVE:
			Type ="CURVE"
		else:
			Type ="LINE"
		#return "<RPoint (%.1f, %.1f %s) for %s.%s[%d][%d]>"%( self._object.position.x, self._object.position.y, Type, FontName, GlyphName, pathIndex, nodeIndex)
		return "<RPoint (%.1f, %.1f %s)>"%( self._object.position.x, self._object.position.y, Type)
	
	def _get_x(self):
		return self._object.x
	
	def _set_x(self, value):
		self._object.setPosition_((value, self._object.position.y))
	
	x = property(_get_x, _set_x, doc="")
	
	def _get_y(self):
		return self._object.y
	
	def _set_y(self, value):
		self._object.setPosition_((self._object.position.x, value))
	
	y = property(_get_y, _set_y, doc="")
	
	def _get_type(self):
		if self._type == MOVE:
			return MOVE
		elif self._object.type == GSOFFCURVE:
			return OFFCURVE
		elif self._object.type == GSCURVE:
			return CURVE
		else:
			return LINE
	
	def _set_type(self, value):
		if value == MOVE:
			self._type = value
		elif value == LINE:
			self._object.type = GSLINE
		elif value == OFFCURVE:
			self._object.type = GSOFFCURVE
		elif value == CURVE:
			self._object.type = GSCURVE
		
		self._hasChanged()

	type = property(_get_type, _set_type, doc="")
	
	def _get_name(self):
		return self._name
	
	def _set_name(self, value):
		self._name = value
		self._hasChanged()

	name = property(_get_name, _set_name, doc="")
	
	def _get_smooth(self):
		return self._smooth
	
	def _set_smooth(self, value):
		self._smooth = value
		self._hasChanged()
	
	smooth = property(_get_smooth, _set_smooth, doc="")
	
	def _get_selected(self):
		Path = self._object.parent
		Layer = Path.parent
		return self._object in Layer.selection()
	
	def _set_selected(self, value):
		Path = self._object.parent
		Layer = Path.parent
		Layer.selection().addObject_(self._object)
		
	selected = property(_get_selected, _set_selected, doc="")
	

class RAnchor(BaseAnchor):
	
	_title = "RoboFabAnchor"
	
	def __init__(self, gs_point=None):
		BaseAnchor.__init__(self)
		self.selected = False
		self.name = gs_point.name
		position = gs_point.position
		if position is None:
			self.x = self.y = None
		else:
			self.x, self.y = position
		
	def _get_index(self):
		if self.getParent() is None: return None
		return self.getParent().anchors.index(self)
	
	index = property(_get_index, doc="index of the anchor")
	
	def _get_position(self):
		return (self.x, self.y)
	
	def _set_position(self, value):
		self.x = value[0]
		self.y = value[1]
		self._hasChanged()
	
	position = property(_get_position, _set_position, doc="position of the anchor")
	
	def move(self, (x, y)):
		"""Move the anchor"""
		self.x = self.x + x
		self.y = self.y + y
		self._hasChanged()

class RComponent(BaseComponent):
	
	_title = "RoboFabComponent"
	
	def __init__(self, baseGlyphName=None, offset=(0,0), scale=(1,1)):
		BaseComponent.__init__(self)
		self.selected = False
		self._baseGlyph = baseGlyphName
		self._offset = offset
		self._scale = scale
		
	def _get_index(self):
		if self.getParent() is None: return None
		return self.getParent().components.index(self)
		
	index = property(_get_index, doc="index of the component")
	
	def _get_baseGlyph(self):
		return self._baseGlyph
		
	def _set_baseGlyph(self, glyphName):
		# XXXX needs to be implemented in objectsFL for symmetricity's sake. Eventually.
		self._baseGlyph = glyphName
		self._hasChanged()
		
	baseGlyph = property(_get_baseGlyph, _set_baseGlyph, doc="")

	def _get_offset(self):
		return self._offset
	
	def _set_offset(self, value):
		self._offset = value
		self._hasChanged()
		
	offset = property(_get_offset, _set_offset, doc="the offset of the component")

	def _get_scale(self):
		return self._scale
	
	def _set_scale(self, (x, y)):
		self._scale = (x, y)
		self._hasChanged()
		
	scale = property(_get_scale, _set_scale, doc="the scale of the component")
		
	def move(self, (x, y)):
		"""Move the component"""
		self.offset = (self.offset[0] + x, self.offset[1] + y)
	
	def decompose(self):
		"""Decompose the component"""
		baseGlyphName = self.baseGlyph
		parentGlyph = self.getParent()
		# if there is no parent glyph, there is nothing to decompose to
		if baseGlyphName is not None and parentGlyph is not None:
			parentFont = parentGlyph.getParent()
			# we must have a parent glyph with the baseGlyph
			# if not, we will simply remove the component from
			# the parent glyph thereby decomposing the component
			# to nothing.
			if parentFont is not None and parentFont.has_key(baseGlyphName):
				from robofab.pens.adapterPens import TransformPointPen
				oX, oY = self.offset
				sX, sY = self.scale
				baseGlyph = parentFont[baseGlyphName]
				for contour in baseGlyph.contours:
					pointPen = parentGlyph.getPointPen()
					transPen = TransformPointPen(pointPen, (sX, 0, 0, sY, oX, oY))
					contour.drawPoints(transPen)
			parentGlyph.components.remove(self)
	
		
class RKerning(BaseKerning):
	
	_title = "RoboFabKerning"

		
class RGroups(BaseGroups):
	
	_title = "RoboFabGroups"
	
class RLib(BaseLib):
	
	_title = "RoboFabLib"

		
class RInfo(BaseInfo):
	
	_title = "GlyphsFontInfo"
	

	def __init__(self, RFontObject):
		#BaseInfo.__init__(self)
		self._object = RFontObject
		#self.baseAttributes = ["_object", "changed", "selected", "getParent"]
		#_renameAttributes = {"openTypeNameManufacturer": "manufacturer"};
	
	def __setattr__(self, attr, value):
		# check to see if the attribute has been
		# deprecated. if so, warn the caller and
		# update the attribute and value.
		
		if attr in self._deprecatedAttributes:
			newAttr, newValue = ufoLib.convertFontInfoValueForAttributeFromVersion1ToVersion2(attr, value)
			note = "The %s attribute has been deprecated. Use the new %s attribute." % (attr, newAttr)
			warn(note, DeprecationWarning)
			attr = newAttr
			value = newValue
		
		_baseAttributes = ["_object", "changed", "selected", "getParent"]
		_renameAttributes = {"openTypeNameManufacturer": "manufacturer",
						  "openTypeNameManufacturerURL": "manufacturerURL",
								 "openTypeNameDesigner": "designer",
							  "openTypeNameDesignerURL": "designerURL",
								  # "openTypeNameLicense": "license",
								  # "openTypeNameLicenseURL": "licenseURL",
											 "fontName": "postscriptFontName",
											"vendorURL": "manufacturerURL",
											 "uniqueID": "postscriptUniqueID",
											"otMacName": "openTypeNameCompatibleFullName" };
		_masterAttributes = ["postscriptUnderlinePosition",
							 "postscriptUnderlineThickness",
							 "openTypeOS2StrikeoutSize",
							 "openTypeOS2StrikeoutPosition"]
		# setting a known attribute
		if attr in _masterAttributes:
			if type(value) == type([]):
				value = NSMutableArray.arrayWithArray_(value)
			elif type(value) == type(1):
				value = NSNumber.numberWithInt_(value)
			elif type(value) == type(1.2):
				value = NSNumber.numberWithFloat_(value)
			
			if attr in _renameAttributes:
				attr = _renameAttributes[attr]
			
			self._object._object.font.fontMasterAtIndex_(self._object._master).setValue_forKey_(value, attr)
			return
			
			
		if attr not in _baseAttributes:
			try:
				if type(value) == type([]):
					value = NSMutableArray.arrayWithArray_(value)
				elif type(value) == type(1):
					value = NSNumber.numberWithInt_(value)
				elif type(value) == type(1.2):
					value = NSNumber.numberWithFloat_(value)
				
				if attr in _renameAttributes:
					attr = _renameAttributes[attr]
					
				self._object._object.font.setValue_forKey_(value, attr)
			except:
				raise AttributeError("Unknown attribute %s." % attr)
			return 

	 	elif attr in self.__dict__ or attr in self._baseAttributes:
			super(BaseInfo, self).__setattr__(attr, value)
		else:
		 	raise AttributeError("Unknown attribute %s." % attr)
	
	def __getattr__(self, attr):
		_baseAttributes = ["_object", "changed", "selected", "getParent"]
		_renameAttributes = {
							 "openTypeNameManufacturer": "manufacturer",
						  "openTypeNameManufacturerURL": "manufacturerURL",
								 "openTypeNameDesigner": "designer",
							  "openTypeNameDesignerURL": "designerURL",
							}
		try:
			gsFont = self._object._object.font
			value = gsFont.valueForKey_(attr)
			if value is None and attr in _renameAttributes:
				value = gsFont.valueForKey_(_renameAttributes[attr])
			if value is None:
				Instance = gsFont.instanceAtIndex_(self._object._master)
				value = Instance.valueForKey_(attr)
				if value is None and attr in _renameAttributes:
					value = Instance.valueForKey_(_renameAttributes[attr])
				if value is None:
					if attr == "postscriptFullName" or attr == "fullName":
						value = "%s-%s" % (gsFont.valueForKey_("familyName"), Instance.name)
					elif attr == "postscriptFontName" or attr == "fontName":
						value = "%s-%s" % (gsFont.valueForKey_("familyName"), Instance.name)
						value = value.replace(" ", "")
			return value
		except:
			raise AttributeError("Unknown attribute %s." % attr)
	

class RFeatures(BaseFeatures):

	_title = "FLFeatures"

	def __init__(self, font):
		super(RFeatures, self).__init__()
		self._object = font
	def _get_text(self):
		naked = self._object
		features = []
		if naked.classes:
			for aClass in naked.classes:
				features.append(aClass.name+" = ["+aClass.code+"];\n")
		features.append("\n")
		features.append(naked.features.text())
		return "".join(features)
	def _set_text(self, value):
		from robofab.tools.fontlabFeatureSplitter import splitFeaturesForFontLab
		classes, features = splitFeaturesForFontLab(value)
		naked = self._object
		for OTClass in classes.splitlines():
			naked.addClassFromCode_( OTClass )
		naked.setFeatures_(None)
		for featureName, featureText in features:
			f = GSFeature()
			f.setName_(featureName)
			f.setCode_(featureText[featureText.find("{")+1: featureText.rfind( "}" )].strip(" \n"))
			naked.addFeature_(f)

	text = property(_get_text, _set_text, doc="raw feature text.")

